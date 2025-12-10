from __future__ import annotations

import asyncio
import logging
import sys
import time
import traceback

try:
    from google.adk.models import google_llm as _google_llm
except Exception:
    _google_llm = None

from poll_agent.config import Settings
from poll_agent.agent import build_runner
from poll_agent.tools.utils import render_events, to_content


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("google_adk").setLevel(logging.ERROR)
    logging.getLogger("google_adk.google_llm").setLevel(logging.ERROR)
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

    async def _ensure_session():
        try:
            await runner.session_service.create_session(
                app_name=settings.app_name,
                user_id=user_id,
                session_id=session_id,
            )
        except Exception:
            return

    asyncio.run(_ensure_session())

    logging.info(
        "[service] started. handles=%s, interval=%ss, agent_model=%s, grok_model=%s",
        settings.default_handles,
        poll_interval,
        settings.agent_model,
        settings.grok_model,
    )

    iteration = 0
    while True:
        iteration += 1
        try:
            logging.info("==== iteration %s begin ====", iteration)
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

            logging.info("calling runner.run")
            events = list(
                runner.run(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=to_content(user_prompt),
                )
            )
            logging.info("events received: %s", len(events))
            logging.info(events)
            for idx, ev in enumerate(events):
                author = getattr(ev, "author", "")
                text = getattr(ev, "content", None)
                summary = ""
                if text and getattr(text, "parts", None):
                    parts_text = []
                    for p in text.parts:
                        if getattr(p, "text", None):
                            parts_text.append(p.text)
                        elif getattr(p, "function_call", None):
                            parts_text.append(f"<function_call {p.function_call.name}>")
                    summary = " | ".join(parts_text)
                logging.info("event[%s] author=%s summary=%s", idx, author, summary)
            final_text, tool_calls = render_events(events)

            for call in tool_calls:
                logging.info("[tool] %s", call)

            logging.info("final response:\n%s", final_text or "No response produced.")
            logging.info("==== iteration %s end ====", iteration)
        except Exception as exc:  # pragma: no cover - service guard
            logging.error("error in iteration %s: %s", iteration, exc)
            traceback.print_exc()

        time.sleep(poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
