from __future__ import annotations

import json
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from poll_agent.config import Settings
from poll_agent.tools.telegram import send_telegram_message


def build_publish_agent(settings: Settings) -> Agent:
    """
    Agent dedicated to publishing poll results to various platforms.
    Currently supports: World Maci api and Telegram
    Future: Discord, Slack, Twitter, etc.

    - send_to_telegram: Wraps send_telegram_message to send poll results to Telegram
    - Agent: Uses Grok model as poll publishing agent
    """

    def send_to_telegram(poll_data: str) -> dict:
        """
        Send poll data to configured Telegram chats.

        Args:
            poll_data: JSON string containing poll data

        Returns:
            dict: Dictionary containing send result
        """
        import logging
        logging.info("[publish_agent] send_to_telegram tool called")
        logging.info(f"[publish_agent] poll_data type: {type(poll_data)}, length: {len(str(poll_data)) if poll_data else 0}")

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
                logging.info("[publish_agent] Parsing poll_data from string")
                # Strip markdown code blocks (```json ... ``` or ``` ... ```)
                cleaned = poll_data.strip()
                if cleaned.startswith("```"):
                    # Remove opening ```json or ```
                    lines = cleaned.split('\n')
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    # Remove closing ```
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = '\n'.join(lines)

                # Fix escaped single quotes \' which are invalid in JSON
                # In JSON, single quotes don't need escaping
                cleaned = cleaned.replace("\\'", "'")

                # Try to parse
                try:
                    data = json.loads(cleaned)
                except json.JSONDecodeError as first_error:
                    # If still fails, try using ast.literal_eval as fallback
                    # This can handle Python-style strings better
                    logging.warning(f"[publish_agent] Standard JSON parse failed: {first_error}, trying fallback...")
                    import ast
                    # Replace True/False with true/false for JSON compatibility
                    fixed = cleaned.replace("False", "false").replace("True", "true")
                    data = json.loads(fixed)
            else:
                logging.info("[publish_agent] Using poll_data as-is (not a string)")
                data = poll_data
            logging.info(f"[publish_agent] Parsed data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"[publish_agent] JSON parse error: {e}")
            logging.error(f"[publish_agent] Failed to parse (first 800 chars): {poll_data[:800] if isinstance(poll_data, str) else poll_data}")
            return {
                "success": False,
                "error": f"Invalid JSON format in poll_data: {str(e)}"
            }

        # Format message for Telegram
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        def html_escape(text):
            """Escape HTML special characters."""
            if not text:
                return ""
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        message_lines = [
            "🗳️ <b>Poll Agent Update</b>",
            f"⏰ {timestamp}",
            "━━━━━━━━━━━━━━━━━━━━\n"
        ]

        # Check if there's actual poll data (poll is now at top level)
        per_handle = data.get("per_handle", [])
        poll = data.get("poll")

        # Find which handle contributed the poll (for display purposes)
        poll_handle = None
        if poll:
            for item in per_handle:
                if item.get("status") == "poll_topic_found":
                    poll_handle = item.get("handle")
                    break

        if poll and poll is not None:
            # Title (engaging question) - support both new "title" and old "topic_title"
            title = poll.get("title") or poll.get("topic_title", "N/A")
            message_lines.append(f"❓<b>Poll title</b>\n<b>{html_escape(title)}</b>\n")

            # Description (what happened) - support both new "description" and old "poll_question"
            description = poll.get("description") or poll.get("poll_question", "N/A")
            message_lines.append(f"📝 <b>Description</b>\n{html_escape(description)}\n")

            # Options
            options = poll.get("options", [])
            if options:
                message_lines.append("📊 <b>Poll Options</b>")
                for i, opt in enumerate(options, 1):
                    message_lines.append(f"   {i}️⃣ {html_escape(opt)}")
                message_lines.append("")

            # Sample posts
            sample_posts = poll.get("sample_posts", [])
            if sample_posts:
                message_lines.append("🔗 <b>Related Posts</b>")
                for post in sample_posts[:3]:  # Show max 3 posts
                    handle = post.get("handle", "unknown")
                    summary = post.get("summary", "")
                    url = post.get("url", "")
                    if url:
                        message_lines.append(f"   • @{html_escape(handle)}: {html_escape(summary)}")
                        message_lines.append(f"     {html_escape(url)}")
                message_lines.append("")

            # Why choose this poll - support both new and old field names
            why_choose = poll.get("why_choose_this_poll") or poll.get("why_safe")
            if why_choose:
                message_lines.append(f"🎯 <b>Why Choose This Poll</b>\n{html_escape(why_choose)}\n")

            # Show source handle and stats
            if poll_handle:
                message_lines.append(f"📍 <b>Source Handle</b>: @{html_escape(poll_handle)}")

            stats = poll.get("stats_snapshot", {})
            if stats:
                message_lines.append(f"📊 <b>Engagement</b>: ❤️{stats.get('likes', 0)} 🔁{stats.get('reposts', 0)} 💬{stats.get('replies', 0)} 👁️{stats.get('views', 0)}")
        else:
            # No poll generated
            explain = data.get("explain", "No suitable poll topic")
            message_lines.append(f"ℹ️ <b>Status</b>\n{html_escape(explain)}\n")

            if per_handle:
                message_lines.append("📊 <b>Handle Status</b>")
                for item in per_handle:
                    handle = item.get("handle", "unknown")
                    stat = item.get("status", "unknown")
                    message_lines.append(f"   • @{html_escape(handle)}: {html_escape(stat)}")

        message_lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        message = "\n".join(message_lines)

        logging.info(f"[publish_agent] Formatted message, length: {len(message)}")
        logging.info(f"[publish_agent] Calling send_telegram_message...")

        result = send_telegram_message(
            message=message,
            telegram_token=settings.telegram_token,
            chat_ids=settings.telegram_chat_ids,
        )

        logging.info(f"[publish_agent] send_telegram_message returned: {result}")
        return result

    instruction_text = (
        "You are the publish_agent responsible for publishing poll results to various platforms.\n\n"
        "Tasks:\n"
        "1. Receive poll data from the main agent (may be JSON string or object)\n"
        "2. Immediately call the send_to_telegram tool to send the data\n"
        "3. Output the sending result\n\n"
        "Note: Send regardless of whether poll data is empty or not. This allows users to confirm the service is running properly."
    )

    # Use LiteLlm to load Grok model
    # LiteLlm uses OpenAI-compatible format for xAI
    import os
    os.environ["XAI_API_KEY"] = settings.xai_api_key

    grok_llm = LiteLlm(
        model=f"xai/{settings.agent_model}",
    )

    return Agent(
        name="publish_agent",
        model=grok_llm,
        instruction=instruction_text,
        description="Publishes poll results to configured platforms (Telegram, etc.).",
        tools=[send_to_telegram],
    )
