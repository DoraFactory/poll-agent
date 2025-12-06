from __future__ import annotations

import json
from google.adk.agents import Agent
from config import Settings
from tools.telegram import send_telegram_message


def build_telegram_agent(settings: Settings) -> Agent:
    """
    Agent dedicated to sending poll results to Telegram.

    - send_to_telegram: 封装 send_telegram_message，发送投票结果到 Telegram
    - Agent: 使用 Gemini 模型作为 Telegram 消息发送代理
    """

    def send_to_telegram(poll_data: str) -> dict:
        """
        Send poll data to configured Telegram chats.

        参数：
        - poll_data: JSON 字符串，包含投票数据

        返回：
        - dict: 包含发送结果的字典
        """
        import logging
        logging.info("[tg_agent] send_to_telegram tool called")
        logging.info(f"[tg_agent] poll_data type: {type(poll_data)}, length: {len(str(poll_data)) if poll_data else 0}")

        if not settings.telegram_token:
            return {
                "success": False,
                "error": "Telegram token not configured. Set TELEGRAM_TOKEN in .env"
            }

        if not settings.telegram_chat_ids:
            return {
                "success": False,
                "error": "No Telegram chat IDs configured. Set TELEGRAM_CHAT_IDS in .env"
            }

        # Parse poll_data if it's a string
        try:
            if isinstance(poll_data, str):
                logging.info("[tg_agent] Parsing poll_data from string")
                data = json.loads(poll_data)
            else:
                logging.info("[tg_agent] Using poll_data as-is (not a string)")
                data = poll_data
            logging.info(f"[tg_agent] Parsed data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": "Invalid JSON format in poll_data"
            }

        # Format message for Telegram
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        message_lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            "🗳️ *Poll Agent 投票更新*",
            f"⏰ {timestamp}",
            "━━━━━━━━━━━━━━━━━━━━\n"
        ]

        # Check if there's actual poll data
        poll = data.get("poll")
        if poll and poll is not None:
            # Poll title
            message_lines.append(f"📊 *主题*\n{poll.get('topic_title', 'N/A')}\n")

            # Poll question
            message_lines.append(f"❓ *投票问题*\n{poll.get('poll_question', 'N/A')}\n")

            # Options
            options = poll.get("options", [])
            if options:
                message_lines.append("📋 *投票选项*")
                for i, opt in enumerate(options, 1):
                    message_lines.append(f"   {i}️⃣ {opt}")
                message_lines.append("")

            # Rationale
            rationale = poll.get("rationale")
            if rationale:
                message_lines.append(f"💡 *选题理由*\n{rationale}\n")

            # Sample posts
            sample_posts = poll.get("sample_posts", [])
            if sample_posts:
                message_lines.append("📝 *相关帖子*")
                for post in sample_posts[:3]:  # Show max 3 posts
                    handle = post.get("handle", "unknown")
                    summary = post.get("summary", "")
                    url = post.get("url", "")
                    if url:
                        message_lines.append(f"   • @{handle}: {summary}")
                        message_lines.append(f"     {url}")
                message_lines.append("")

            # Covered handles
            handles = poll.get("handles_covered", [])
            if handles:
                message_lines.append(f"👥 *监测账号*: {', '.join(['@' + h for h in handles])}")
        else:
            # No poll generated
            explain = data.get("explain", "无合适的投票话题")
            message_lines.append(f"ℹ️ *状态*\n{explain}\n")

            per_handle = data.get("per_handle_status", [])
            if per_handle:
                message_lines.append("📊 *各账号状态*")
                for status in per_handle:
                    handle = status.get("handle", "unknown")
                    stat = status.get("status", "unknown")
                    message_lines.append(f"   • @{handle}: {stat}")

        message_lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        message = "\n".join(message_lines)

        logging.info(f"[tg_agent] Formatted message, length: {len(message)}")
        logging.info(f"[tg_agent] Calling send_telegram_message...")

        result = send_telegram_message(
            message=message,
            telegram_token=settings.telegram_token,
            chat_ids=settings.telegram_chat_ids,
        )

        logging.info(f"[tg_agent] send_telegram_message returned: {result}")
        return result

    instruction_text = (
        "你是负责将投票结果发送到 Telegram 的子代理（telegram_agent）。\n\n"
        "任务：\n"
        "1. 接收主代理传递的投票数据（可能是 JSON 字符串或对象）\n"
        "2. 立即调用 send_to_telegram 工具发送数据\n"
        "3. 输出发送结果\n\n"
        "注意：无论投票数据是否为空，都要发送。这样用户可以确认服务正常运行。"
    )

    return Agent(
        name="telegram_agent",
        model=settings.gemini_model,
        instruction=instruction_text,
        description="Sends poll results to configured Telegram chats.",
        tools=[send_to_telegram],
    )
