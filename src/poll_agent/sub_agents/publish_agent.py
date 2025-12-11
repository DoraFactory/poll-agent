from __future__ import annotations

import json
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from poll_agent.config import Settings
from poll_agent.tools.telegram import send_telegram_message
from poll_agent.tools.push_chain import push_poll_to_chain
from poll_agent.tools.push_x import push_poll_to_x


def build_publish_agent(settings: Settings) -> Agent:
    """
    Agent dedicated to publishing poll results to various platforms.
    Currently supports: World MACI API, Twitter (X), and Telegram

    Tools:
    1. push_to_chain: Push poll to World MACI API, returns contract address
    2. push_to_x: Post poll announcement to Twitter/X with vote URL
    3. send_to_telegram: Send poll (with optional contract address and tweet URL) to Telegram

    - Agent: Uses Grok model as poll publishing agent
    """

    def push_to_chain(poll_data: str) -> dict:
        """
        Push poll to World MACI API to create on-chain contract.

        Purpose:
            Deploy poll to blockchain via World MACI API and obtain contract address.

        When to call:
            - Call FIRST when there is a valid poll in poll_data
            - Call BEFORE send_to_telegram so contract address can be included in message
            - Skip if poll_data contains no valid poll (null poll field)

        Args:
            poll_data (str): JSON string containing complete poll data structure:
                {
                    "per_handle": [...],
                    "poll": {
                        "title": "Poll question",
                        "description": "Poll description",
                        "options": ["Option 1", "Option 2"],
                        ...
                    }
                }

        Returns:
            dict: Result of chain push operation
                On success:
                {
                    "success": true,
                    "contract_address": "0xABC123..."
                }
                On failure:
                {
                    "success": false,
                    "error": "Error message describing what went wrong"
                }

        Success behavior:
            - Extract contract_address from result
            - Pass it to send_to_telegram tool for display
            - Log success message

        Failure behavior:
            - Log error message
            - Continue with send_to_telegram anyway (without contract address)
            - User should see error in logs but Telegram message still sent
        """
        import logging
        logging.info("[publish_agent] push_to_chain tool called")
        logging.info(f"[publish_agent] Input: poll_data length={len(poll_data) if poll_data else 0}")

        # Step 1: Parse poll_data JSON
        logging.info("[publish_agent] Step 1: Parsing poll_data JSON")
        try:
            if isinstance(poll_data, str):
                cleaned = poll_data.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split('\n')
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = '\n'.join(lines)
                cleaned = cleaned.replace("\\'", "'")
                data = json.loads(cleaned)
                logging.info("[publish_agent] JSON parsed successfully")
            else:
                data = poll_data
                logging.info("[publish_agent] Using poll_data as dict directly")
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Invalid JSON format: {str(e)}"
            logging.error(f"[publish_agent] FAILURE: {error_msg}")
            logging.error("[publish_agent] Action: Returning failure, agent should NOT call send_to_telegram with invalid data")
            return {
                "success": False,
                "error": error_msg
            }

        # Step 2: Extract poll from data
        logging.info("[publish_agent] Step 2: Extracting poll from data")
        poll = data.get("poll")
        if not poll:
            error_msg = "No poll found in data"
            logging.warning(f"[publish_agent] FAILURE: {error_msg}")
            logging.warning("[publish_agent] Action: Returning failure, agent should call send_to_telegram without contract_address")
            return {
                "success": False,
                "error": error_msg
            }

        # Step 3: Validate poll fields
        logging.info("[publish_agent] Step 3: Validating poll fields")
        title = poll.get("title", "")
        description = poll.get("description", "")
        options = poll.get("options", [])

        if not title or not options:
            error_msg = f"Poll missing required fields: title={bool(title)}, options={len(options)}"
            logging.error(f"[publish_agent] FAILURE: {error_msg}")
            logging.error("[publish_agent] Action: Returning failure, agent should call send_to_telegram without contract_address")
            return {
                "success": False,
                "error": error_msg
            }

        logging.info(f"[publish_agent] Poll validated: title='{title}', options={len(options)}")

        # Step 4: Call World MACI API
        logging.info("[publish_agent] Step 4: Calling World MACI API to deploy poll on-chain")
        result = push_poll_to_chain(
            poll_title=title,
            poll_description=description,
            voting_options=options,
            api_endpoint=settings.world_maci_api_endpoint,
            api_token=settings.world_maci_api_token,
        )

        if result.get("success"):
            contract_address = result.get("contract_address", "")
            logging.info(f"[publish_agent] SUCCESS: Poll deployed to chain at {contract_address}")
            logging.info("[publish_agent] Action: Agent should extract contract_address and pass it to send_to_telegram")
        else:
            error = result.get("error", "Unknown error")
            logging.error(f"[publish_agent] FAILURE: Chain push failed - {error}")
            logging.error("[publish_agent] Action: Agent should still call send_to_telegram (without contract_address)")

        return result

    def push_to_x(poll_data: str, vote_url: str) -> dict:
        """
        Post poll announcement to X (Twitter) using Twitter API v2.

        Purpose:
            Publish poll notification to Twitter to increase visibility and engagement.
            Posts a tweet with poll title, options, and voting link.

        When to call:
            - Call AFTER push_to_chain succeeds and vote_url is constructed
            - Call BEFORE send_to_telegram so tweet URL can be included in Telegram message
            - Skip if Twitter credentials are not configured

        Args:
            poll_data (str): JSON string containing complete poll data structure:
                {
                    "per_handle": [...],
                    "poll": {
                        "title": "Poll question",
                        "description": "Poll description",
                        "options": ["Option 1", "Option 2"],
                        ...
                    }
                }

            vote_url (str): Complete voting URL (world_maci_vote_url + contract_address)
                Example: "https://vota-test.dorafactory.org/round/0xABC123..."

        Returns:
            dict: Result of Twitter post operation
                On success:
                {
                    "success": true,
                    "tweet_id": "1234567890",
                    "tweet_url": "https://twitter.com/i/web/status/1234567890"
                }
                On failure:
                {
                    "success": false,
                    "error": "Error message"
                }

        Success behavior:
            - Extract tweet_url from result
            - Pass it to send_to_telegram tool for display
            - Log success message

        Failure behavior:
            - Log error message
            - Continue with send_to_telegram anyway (without tweet URL)
            - Include error in Telegram message for visibility
        """
        import logging
        logging.info("[publish_agent] push_to_x tool called")
        logging.info(f"[publish_agent] Input: poll_data length={len(poll_data) if poll_data else 0}")
        logging.info(f"[publish_agent] Input: vote_url={vote_url}")

        # Step 1: Parse poll_data JSON
        logging.info("[publish_agent] Step 1: Parsing poll_data JSON")
        try:
            if isinstance(poll_data, str):
                cleaned = poll_data.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split('\n')
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = '\n'.join(lines)
                cleaned = cleaned.replace("\\'", "'")
                data = json.loads(cleaned)
                logging.info("[publish_agent] JSON parsed successfully")
            else:
                data = poll_data
                logging.info("[publish_agent] Using poll_data as dict directly")
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Invalid JSON format: {str(e)}"
            logging.error(f"[publish_agent] FAILURE: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

        # Step 2: Extract poll from data
        logging.info("[publish_agent] Step 2: Extracting poll from data")
        poll = data.get("poll")
        if not poll:
            error_msg = "No poll found in data"
            logging.warning(f"[publish_agent] FAILURE: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

        # Step 3: Validate poll fields
        logging.info("[publish_agent] Step 3: Validating poll fields")
        title = poll.get("title", "")
        description = poll.get("description", "")
        options = poll.get("options", [])

        if not title or not options:
            error_msg = f"Poll missing required fields: title={bool(title)}, options={len(options)}"
            logging.error(f"[publish_agent] FAILURE: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

        logging.info(f"[publish_agent] Poll validated: title='{title}', options={len(options)}")

        # Step 4: Call Twitter API
        logging.info("[publish_agent] Step 4: Calling Twitter API to post poll announcement")
        result = push_poll_to_x(
            poll_title=title,
            poll_description=description,
            voting_options=options,
            vote_url=vote_url,
            api_key=settings.twitter_api_key,
            api_secret=settings.twitter_api_secret,
            access_token=settings.twitter_access_token,
            access_token_secret=settings.twitter_access_token_secret,
        )

        if result.get("success"):
            tweet_url = result.get("tweet_url", "")
            logging.info(f"[publish_agent] SUCCESS: Poll posted to Twitter at {tweet_url}")
            logging.info("[publish_agent] Action: Agent should extract tweet_url and pass it to send_to_telegram")
        else:
            error = result.get("error", "Unknown error")
            logging.error(f"[publish_agent] FAILURE: Twitter post failed - {error}")
            logging.error("[publish_agent] Action: Agent should still call send_to_telegram (without tweet_url)")

        return result

    def send_to_telegram(poll_data: str, contract_address: str = "", chain_push_error: str = "", tweet_url: str = "", twitter_push_error: str = "") -> dict:
        """
        Send formatted poll notification to configured Telegram chats.

        Purpose:
            Format poll data into HTML message and send to all configured Telegram channels.
            Include on-chain contract address, Twitter post link if available.

        When to call:
            - Call AFTER push_to_chain and push_to_x (if poll exists)
            - Call ALWAYS, even if push_to_chain or push_to_x failed or were skipped
            - This is the final step - always execute to notify users

        Args:
            poll_data (str): JSON string containing complete poll data structure:
                {
                    "per_handle": [
                        {"handle": "cb_doge", "status": "poll_topic_found", "post_count": 5},
                        ...
                    ],
                    "poll": {
                        "title": "Poll question",
                        "description": "Detailed description",
                        "options": ["Option 1", "Option 2"],
                        "sample_posts": [...],
                        "why_choose_this_poll": "Reason for selection",
                        "stats_snapshot": {"likes": 100, "reposts": 50, ...}
                    }
                }
                Note: poll can be null if no suitable topic found

            contract_address (str, optional): Blockchain contract address from push_to_chain.
                - If provided: Display in message as "⛓️ On-Chain Contract: 0x..."
                - If empty: Check chain_push_error to determine status
                - Default: ""

            chain_push_error (str, optional): Error message if chain push failed.
                - If provided: Display failure message in Telegram
                - If empty and contract_address empty: Chain push was skipped (no API configured)
                - Default: ""

            tweet_url (str, optional): Twitter post URL from push_to_x.
                - If provided: Display clickable link to Twitter post
                - If empty: Check twitter_push_error to determine status
                - Default: ""

            twitter_push_error (str, optional): Error message if Twitter push failed.
                - If provided: Display failure message in Telegram
                - If empty and tweet_url empty: Twitter push was skipped (no credentials configured)
                - Default: ""

        Returns:
            dict: Result of Telegram send operation
                On success:
                {
                    "success": true,
                    "sent_count": 2,
                    "total_chats": 2,
                    "details": [
                        {"chat_id": "123", "success": true},
                        {"chat_id": "456", "success": true}
                    ]
                }
                On partial success:
                {
                    "success": true,  # At least one succeeded
                    "sent_count": 1,
                    "total_chats": 2,
                    "details": [
                        {"chat_id": "123", "success": true},
                        {"chat_id": "456", "success": false, "error": "HTTP 403"}
                    ]
                }
                On complete failure:
                {
                    "success": false,
                    "error": "No Telegram chat IDs configured"
                }

        Success behavior:
            - Log success message with sent count
            - Return success=true with details
            - Agent should output final result to user

        Failure behavior:
            - Log error message with failure reason
            - Return success=false with error description
            - Agent should report failure to user
            - DO NOT retry automatically
        """
        import logging
        logging.info("[publish_agent] send_to_telegram tool called")
        logging.info(f"[publish_agent] Input: poll_data length={len(str(poll_data)) if poll_data else 0}")
        if contract_address:
            logging.info(f"[publish_agent] Input: contract_address={contract_address}")
        elif chain_push_error:
            logging.info(f"[publish_agent] Input: chain_push_error={chain_push_error}")
        else:
            logging.info("[publish_agent] Input: No contract_address or error (chain push skipped)")

        if tweet_url:
            logging.info(f"[publish_agent] Input: tweet_url={tweet_url}")
        elif twitter_push_error:
            logging.info(f"[publish_agent] Input: twitter_push_error={twitter_push_error}")
        else:
            logging.info("[publish_agent] Input: No tweet_url or error (Twitter push skipped)")

        # Step 1: Validate Telegram configuration
        logging.info("[publish_agent] Step 1: Validating Telegram configuration")
        if not settings.telegram_token:
            error_msg = "Telegram token not configured. Set TELEGRAM_TOKEN in .env"
            logging.error(f"[publish_agent] FAILURE: {error_msg}")
            logging.error("[publish_agent] Action: Returning failure, agent should report configuration error to user")
            return {
                "success": False,
                "error": error_msg
            }

        if not settings.telegram_chat_ids:
            error_msg = "No Telegram chat IDs configured. Set TELEGRAM_CHAT_IDS in .env"
            logging.error(f"[publish_agent] FAILURE: {error_msg}")
            logging.error("[publish_agent] Action: Returning failure, agent should report configuration error to user")
            return {
                "success": False,
                "error": error_msg
            }

        logging.info(f"[publish_agent] Configuration validated: {len(settings.telegram_chat_ids)} chat(s) configured")

        # Step 2: Parse poll_data JSON
        logging.info("[publish_agent] Step 2: Parsing poll_data JSON")
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
                logging.info("[publish_agent] Using poll_data as dict directly")
                data = poll_data
            logging.info(f"[publish_agent] JSON parsed successfully, keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Invalid JSON format in poll_data: {str(e)}"
            logging.error(f"[publish_agent] FAILURE: {error_msg}")
            logging.error(f"[publish_agent] First 800 chars: {poll_data[:800] if isinstance(poll_data, str) else poll_data}")
            logging.error("[publish_agent] Action: Returning failure, agent should report parse error to user")
            return {
                "success": False,
                "error": error_msg
            }

        # Step 3: Format message for Telegram
        logging.info("[publish_agent] Step 3: Formatting Telegram message")
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

        # Extract poll data
        per_handle = data.get("per_handle", [])
        poll = data.get("poll")

        if poll:
            logging.info("[publish_agent] Poll found, formatting poll details")
        else:
            logging.info("[publish_agent] No poll found, formatting status message")

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

            # Show on-chain status
            message_lines.append("")  # Empty line for separation
            if contract_address:
                # Chain push succeeded - construct vote URL
                vote_base_url = settings.world_maci_vote_url
                if not vote_base_url.endswith('/'):
                    vote_base_url += '/'
                vote_url = f"{vote_base_url}{contract_address}"
                message_lines.append(f"\n🔥🔥🔥 <b><u>P O L L   P U B L I S H E D  </u></b> 🔥🔥🔥")
                message_lines.append(f"👇👇👇")
                message_lines.append(f"<a href='{vote_url}'><b>🗳️ 👉 C L I C K   T O   V O T E 👈 🗳️</b></a>")
                message_lines.append(f"👆👆👆")
            elif chain_push_error:
                # Chain push attempted but failed
                message_lines.append(f"⛓️ <b>Publish Poll</b>: ❌ Failed")
                message_lines.append(f"   <b>Error</b>: {html_escape(chain_push_error)}")
            else:
                # Chain push not configured or skipped
                message_lines.append(f"⛓️ <b>Publish Poll</b>: ⏭️ Skipped")
                message_lines.append(f"   <i>(World MACI API not configured)</i>")

            # Show Twitter status
            message_lines.append("")  # Empty line for separation
            if tweet_url:
                # Twitter push succeeded
                message_lines.append(f"🐦 <b>Posted to X (Twitter)</b>: ✅ Success")
                message_lines.append(f"   <a href='{tweet_url}'>View Tweet</a>")
            elif twitter_push_error:
                # Twitter push attempted but failed
                message_lines.append(f"🐦 <b>Posted to X (Twitter)</b>: ❌ Failed")
                message_lines.append(f"   <b>Error</b>: {html_escape(twitter_push_error)}")
            else:
                # Twitter push not configured or skipped
                message_lines.append(f"🐦 <b>Posted to X (Twitter)</b>: ⏭️ Skipped")
                message_lines.append(f"   <i>(Twitter API credentials not configured)</i>")
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

        logging.info(f"[publish_agent] Message formatted successfully, length: {len(message)} chars")

        # Step 4: Send message to Telegram
        logging.info(f"[publish_agent] Step 4: Sending message to {len(settings.telegram_chat_ids)} Telegram chat(s)")
        result = send_telegram_message(
            message=message,
            telegram_token=settings.telegram_token,
            chat_ids=settings.telegram_chat_ids,
        )

        # Step 5: Process result
        if result.get("success"):
            sent_count = result.get("sent_count", 0)
            total_chats = result.get("total_chats", 0)
            logging.info(f"[publish_agent] SUCCESS: Message sent to {sent_count}/{total_chats} chat(s)")
            logging.info("[publish_agent] Action: Agent should output success result to user")
        else:
            error = result.get("error", "Unknown error")
            logging.error(f"[publish_agent] FAILURE: Failed to send message - {error}")
            logging.error("[publish_agent] Action: Agent should report Telegram send failure to user")

        return result

    instruction_text = (
        "You are the publish_agent responsible for publishing poll results to various platforms.\n\n"
        "Workflow:\n"
        "1. Receive poll data from the main agent (may be JSON string or object)\n"
        "2. If there is a valid poll:\n"
        "   a. Call push_to_chain(poll_data) to deploy poll on-chain\n"
        "      - If success=true: Extract contract_address from result\n"
        "      - If success=false: Extract error message from result\n"
        "   b. If push_to_chain succeeded (has contract_address):\n"
        "      - Construct vote_url = world_maci_vote_url + contract_address\n"
        "      - Call push_to_x(poll_data, vote_url) to post on Twitter\n"
        "      - If success=true: Extract tweet_url from result\n"
        "      - If success=false: Extract error message from result\n"
        "   c. Call send_to_telegram with all collected parameters:\n"
        "      - Full success: send_to_telegram(poll_data, contract_address=<addr>, tweet_url=<url>)\n"
        "      - Chain only: send_to_telegram(poll_data, contract_address=<addr>, twitter_push_error=<error>)\n"
        "      - Chain failed: send_to_telegram(poll_data, chain_push_error=<error>)\n"
        "3. If no valid poll, just call send_to_telegram(poll_data)\n"
        "4. Output the final result\n\n"
        "IMPORTANT:\n"
        "- ALWAYS call send_to_telegram regardless of push_to_chain or push_to_x result\n"
        "- Only call push_to_x if push_to_chain succeeded (need vote_url)\n"
        "- Pass all status information to send_to_telegram so users see what happened\n"
        "- Don't construct vote_url yourself - it's world_maci_vote_url + '/' + contract_address"
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
        include_contents='none',
        instruction=instruction_text,
        description="Publishes poll results to configured platforms (World MACI API + Twitter/X + Telegram).",
        tools=[push_to_chain, push_to_x, send_to_telegram],
    )
