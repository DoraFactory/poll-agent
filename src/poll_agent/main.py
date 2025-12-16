from __future__ import annotations

import asyncio
import logging
import sys
import time
import traceback
import uuid

try:
    from google.adk.models import google_llm as _google_llm
except Exception:
    _google_llm = None

from poll_agent.config import Settings
from poll_agent.agent import build_runner
from poll_agent.monitoring import log_metric
from poll_agent.tools.utils import render_events, to_content


def _truncate_for_log(text: str, max_len: int = 900) -> str:
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}…<truncated len={len(text)}>"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("google_adk").setLevel(logging.ERROR)
    logging.getLogger("google_adk.google_llm").setLevel(logging.ERROR)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)
    if _google_llm is not None:
        _google_llm._build_request_log = lambda _req: "<request log suppressed>"

    settings = Settings()
    settings.require_keys()

    if not settings.default_handles:
        logging.error("X_HANDLES not configured: Please provide at least one handle in .env or environment variables.")
        return 1

    poll_interval = settings.poll_interval_seconds
    user_id = "poll-agent-admin"
    session_id = "poll-session"
    base_prompt = (
        "Fetch the latest posts from these accounts within the specified time window, identify the most poll-worthy trending topic, and generate a poll draft."
        "Workflow:\n"
        "1. Call x_feed_agent to fetch data (via grok_recent_posts)\n"
        "2. Generate poll JSON\n"
        "3. MUST call publish_agent to publish results to configured platforms\n"
        "4. Output final JSON\n"
        "Note: Even if there are no new posts, a notification must be sent to confirm the service is running properly."
    )

    runner = build_runner(settings)

    def _ensure_session():
        """Create the ADK session if missing."""
        session_service = runner.session_service

        if hasattr(session_service, "get_session_sync") and hasattr(session_service, "create_session_sync"):
            try:
                existing = session_service.get_session_sync(
                    app_name=settings.app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
                if existing:
                    return
                session_service.create_session_sync(
                    app_name=settings.app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
                return
            except Exception as exc:
                logging.warning("Sync session ensure failed; falling back to async: %s", exc)

        async def _ensure_async() -> None:
            existing = await session_service.get_session(
                app_name=settings.app_name,
                user_id=user_id,
                session_id=session_id,
            )
            if existing:
                return
            await session_service.create_session(
                app_name=settings.app_name,
                user_id=user_id,
                session_id=session_id,
            )

        try:
            asyncio.run(_ensure_async())
        except RuntimeError:
            import threading

            exc_holder: list[BaseException] = []

            def _thread_main() -> None:
                try:
                    asyncio.run(_ensure_async())
                except BaseException as exc:  # pragma: no cover - defensive
                    exc_holder.append(exc)

            thread = threading.Thread(target=_thread_main, daemon=True)
            thread.start()
            thread.join(timeout=10)
            if exc_holder:
                raise exc_holder[0]

    _ensure_session()

    logging.info(
        "[service] started. handles=%s, interval=%ss, agent_model=%s, grok_model=%s",
        settings.default_handles,
        poll_interval,
        settings.agent_model,
        settings.grok_model,
    )

    run_once = settings.run_once
    iteration = 0
    while True:
        iteration += 1
        run_id = str(uuid.uuid4())
        run_start = time.time()
        iteration_ok = False
        user_prompt = ""
        try:
            logging.info("[main] iteration %s begin", iteration)
            log_metric(
                "poll_agent.run_start",
                run_id=run_id,
                iteration=iteration,
                poll_interval_seconds=poll_interval,
                handles=settings.default_handles,
            )
            user_prompt = (
                f"{base_prompt}\n"
                f"Handles: {', '.join(settings.default_handles)}\n"
                f"Time window: Posts from the last {poll_interval} seconds.\n\n"
                "【Required Two Calls】:\n"
                "1. Call x_feed_agent (transfer_to_agent) to fetch data\n"
                "2. Call publish_agent (transfer_to_agent) to publish results\n\n"
                "【IMPORTANT】Both agents MUST be called! Do not end after only calling x_feed_agent.\n"
                "Publishing must be completed before outputting the final JSON."
            )

            events = list(
                runner.run(user_id=user_id, session_id=session_id, new_message=to_content(user_prompt))
            )
            final_text, tool_calls = render_events(events)

            for call in tool_calls:
                logging.info("[agent=poll_orchestrator] %s", call)

            if final_text:
                logging.info("[agent=poll_orchestrator] final response: %s", _truncate_for_log(final_text))
            else:
                logging.warning("[agent=poll_orchestrator] no final response produced.")

            log_metric(
                "poll_agent.run_end",
                run_id=run_id,
                iteration=iteration,
                success=True,
                duration_seconds=round(time.time() - run_start, 3),
                tool_calls=len(tool_calls),
                has_final_text=bool(final_text),
            )
            iteration_ok = True
            logging.info("[main] iteration %s end", iteration)
        except Exception as exc:  # pragma: no cover - service guard
            if isinstance(exc, ValueError) and "Session not found:" in str(exc):
                logging.warning("session missing; recreating and retrying once: %s", exc)
                try:
                    _ensure_session()
                    events = list(
                        runner.run(user_id=user_id, session_id=session_id, new_message=to_content(user_prompt))
                    )
                    final_text, tool_calls = render_events(events)

                    for call in tool_calls:
                        logging.info("[agent=poll_orchestrator] %s", call)

                    if final_text:
                        logging.info("[agent=poll_orchestrator] final response: %s", _truncate_for_log(final_text))
                    else:
                        logging.warning("[agent=poll_orchestrator] no final response produced.")

                    log_metric(
                        "poll_agent.run_end",
                        run_id=run_id,
                        iteration=iteration,
                        success=True,
                        duration_seconds=round(time.time() - run_start, 3),
                        tool_calls=len(tool_calls),
                        has_final_text=bool(final_text),
                        retried_session=True,
                    )
                    iteration_ok = True
                    logging.info("[main] iteration %s end", iteration)
                except Exception as retry_exc:
                    logging.error("retry after session recreate failed: %s", retry_exc)
                    traceback.print_exc()

            log_metric(
                "poll_agent.run_end",
                run_id=run_id,
                iteration=iteration,
                success=False,
                duration_seconds=round(time.time() - run_start, 3),
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
            logging.error("error in iteration %s: %s", iteration, exc)
            traceback.print_exc()

        if run_once:
            return 0 if iteration_ok else 1

        time.sleep(poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
