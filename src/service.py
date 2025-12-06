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

from config import Settings
from runner import build_runner
from tools.utils import render_events, to_content
from tools.telegram import send_telegram_message


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

    settings.gemini_model = settings.gemini_model.lstrip("= ").strip()
    safe_models = [
        "gemini-2.5-pro",
        "gemini-2.0-pro",
        "gemini-2.0-flash",
    ]
    if settings.gemini_model not in safe_models:
        logging.warning(
            "GEMINI_MODEL '%s' unsupported by ADK registry. Falling back to %s.",
            settings.gemini_model,
            safe_models[0],
        )
        settings.gemini_model = safe_models[0]

    if not settings.default_handles:
        logging.error("X_HANDLES 未配置：请在 .env 或环境变量中提供至少一个 handle。")
        return 1

    poll_interval = settings.poll_interval_seconds
    user_id = "poll-agent-admin"
    session_id = "poll-session"
    base_prompt = (
        "请抓取这些账号在指定时间窗口内的最新帖子，找出当前最值得投票的热点话题，并生成投票草案。"
        "工作流程：\n"
        "1. 调用 x_feed_agent 获取数据（通过 grok_recent_posts）\n"
        "2. 生成投票 JSON\n"
        "3. 必须调用 telegram_agent 将结果发送到 Telegram\n"
        "4. 输出最终 JSON\n"
        "注意：即使没有新帖子，也必须发送 Telegram 通知以确认服务正常运行。"
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
        "[service] started. handles=%s, interval=%ss, model=%s, grok_model=%s",
        settings.default_handles,
        poll_interval,
        settings.gemini_model,
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
                f"时间窗口：最近 {poll_interval} 秒内的帖子。\n\n"
                "【必须完成的两个调用】：\n"
                "1. 调用 x_feed_agent（transfer_to_agent）获取数据\n"
                "2. 调用 telegram_agent（transfer_to_agent）发送结果\n\n"
                "【重要】两个 agent 都必须调用！不要只调用 x_feed_agent 就结束了。\n"
                "在输出最终 JSON 之前，必须先完成 Telegram 发送。"
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

            # Send Telegram notification
            if settings.telegram_token and settings.telegram_chat_ids:
                try:
                    logging.info("[service] Sending Telegram notification...")
                    import json
                    from datetime import datetime, timezone

                    # Try to parse the final_text as JSON
                    try:
                        if final_text and final_text.strip():
                            # Remove markdown code blocks if present
                            clean_text = final_text.strip()

                            # Remove leading ```json or ```
                            if clean_text.startswith("```json"):
                                clean_text = clean_text[7:]
                            elif clean_text.startswith("```"):
                                clean_text = clean_text[3:]

                            # Remove trailing ```
                            if clean_text.endswith("```"):
                                clean_text = clean_text[:-3]

                            clean_text = clean_text.strip()

                            logging.info(f"[service] Cleaned JSON text (first 100 chars): {clean_text[:100]}")
                            data = json.loads(clean_text)
                            logging.info(f"[service] Successfully parsed JSON with keys: {list(data.keys())}")
                        else:
                            data = {"explain": "No response produced"}
                    except json.JSONDecodeError as e:
                        logging.warning(f"[service] Failed to parse response as JSON: {e}")
                        logging.warning(f"[service] Problematic text (first 200 chars): {clean_text[:200] if 'clean_text' in locals() else final_text[:200]}")
                        data = {"explain": "Invalid JSON response"}

                    # Format message
                    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                    message_lines = [
                        "━━━━━━━━━━━━━━━━━━━━",
                        "🗳️ *Poll Agent 投票更新*",
                        f"⏰ {timestamp}",
                        "━━━━━━━━━━━━━━━━━━━━\n"
                    ]

                    # Check for poll in per_handle
                    per_handle = data.get("per_handle", [])
                    poll_found = False

                    for item in per_handle:
                        poll = item.get("poll")
                        if poll:
                            poll_found = True
                            message_lines.append(f"📊 *主题*\n{poll.get('topic_title', 'N/A')}\n")
                            message_lines.append(f"❓ *投票问题*\n{poll.get('poll_question', 'N/A')}\n")

                            options = poll.get("options", [])
                            if options:
                                message_lines.append("📋 *投票选项*")
                                for i, opt in enumerate(options, 1):
                                    message_lines.append(f"   {i}️⃣ {opt}")
                                message_lines.append("")

                            sample_posts = poll.get("sample_posts", [])
                            if sample_posts:
                                message_lines.append("📝 *相关帖子*")
                                for post in sample_posts[:3]:
                                    handle = post.get("handle", "unknown")
                                    summary = post.get("summary", "")
                                    url = post.get("url", "")
                                    if url:
                                        message_lines.append(f"   • @{handle}: {summary}")
                                        message_lines.append(f"     {url}")
                                message_lines.append("")
                            break

                    if not poll_found:
                        message_lines.append("ℹ️ *状态*\n本轮未找到合适的投票话题\n")
                        if per_handle:
                            message_lines.append("📊 *各账号状态*")
                            for item in per_handle:
                                handle = item.get("handle", "unknown")
                                status = item.get("status", "unknown")
                                message_lines.append(f"   • @{handle}: {status}")

                    message_lines.append("\n━━━━━━━━━━━━━━━━━━━━")
                    message = "\n".join(message_lines)

                    result = send_telegram_message(
                        message=message,
                        telegram_token=settings.telegram_token,
                        chat_ids=settings.telegram_chat_ids,
                    )
                    logging.info(f"[service] Telegram notification result: {result}")
                except Exception as e:
                    logging.error(f"[service] Failed to send Telegram notification: {e}")
            else:
                logging.info("[service] Telegram not configured, skipping notification")

            logging.info("==== iteration %s end ====", iteration)
        except Exception as exc:  # pragma: no cover - service guard
            logging.error("error in iteration %s: %s", iteration, exc)
            traceback.print_exc()

        time.sleep(poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
