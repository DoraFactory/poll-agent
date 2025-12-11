"""Push poll data to X (Twitter) using Twitter API v2."""

from __future__ import annotations

import logging
from typing import Dict, Any

try:
    import requests
    from requests_oauthlib import OAuth1
except ImportError:
    requests = None
    OAuth1 = None


def push_poll_to_x(
    poll_title: str,
    poll_description: str,
    voting_options: list[str],
    vote_url: str,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
) -> Dict[str, Any]:
    """
    Post poll announcement to X (Twitter) using Twitter API v2.

    Purpose:
        Publish poll notification to Twitter to increase visibility and engagement.

    When to call:
        - Call AFTER push_to_chain succeeds and vote_url is available
        - Call BEFORE send_to_telegram (or in parallel)
        - Skip if Twitter credentials are not configured

    Args:
        poll_title: The poll question/title
        poll_description: Detailed description of the poll
        voting_options: List of voting options
        vote_url: Complete voting URL (base_url + contract_address)
        api_key: Twitter API Key (Consumer Key)
        api_secret: Twitter API Secret (Consumer Secret)
        access_token: Twitter Access Token
        access_token_secret: Twitter Access Token Secret

    Returns:
        On success: {"success": true, "tweet_id": "1234567890", "tweet_url": "https://twitter.com/user/status/1234567890"}
        On failure: {"success": false, "error": "Error message"}

    Success behavior:
        - Tweet is posted to authenticated account
        - Returns tweet ID and public URL
        - Agent should include tweet URL in Telegram notification

    Failure behavior:
        - Log error with details
        - Continue with other publishing (don't block Telegram)
        - Include error in final notification
    """
    logging.info("[push_x] push_poll_to_x called")
    logging.info(f"[push_x] title: {poll_title}")

    # Validate credentials
    if not all([api_key, api_secret, access_token, access_token_secret]):
        return {
            "success": False,
            "error": "Twitter API credentials not fully configured"
        }

    if requests is None or OAuth1 is None:
        return {
            "success": False,
            "error": "requests or requests_oauthlib library not available"
        }

    try:
        # Construct tweet text
        # Twitter API v2 allows up to 280 characters
        options_text = " | ".join(voting_options)

        # Build tweet with poll info and vote link
        tweet_lines = [
            f"🗳️ New Poll: {poll_title}",
            "",
            f"Options: {options_text}",
            "",
            f"🔥 Vote now: {vote_url}"
        ]

        tweet_text = "\n".join(tweet_lines)

        # Truncate if too long (keep some buffer for safety)
        if len(tweet_text) > 280:
            # Simplified version if text is too long
            tweet_text = f"🗳️ New Poll: {poll_title}\n\n🔥 Vote now: {vote_url}"

        if len(tweet_text) > 280:
            # Even more simplified if still too long
            short_title = poll_title[:200] + "..." if len(poll_title) > 200 else poll_title
            tweet_text = f"🗳️ {short_title}\n\nVote: {vote_url}"

        logging.info(f"[push_x] Tweet text ({len(tweet_text)} chars): {tweet_text}")

        # Set up OAuth 1.0a authentication
        auth = OAuth1(
            api_key,
            api_secret,
            access_token,
            access_token_secret
        )

        # Twitter API v2 endpoint for creating tweets
        url = "https://api.twitter.com/2/tweets"

        payload = {
            "text": tweet_text
        }

        response = requests.post(
            url,
            auth=auth,
            json=payload,
            timeout=30
        )

        if response.status_code == 201:
            result = response.json()
            tweet_data = result.get("data", {})
            tweet_id = tweet_data.get("id", "")

            # Construct tweet URL (need to know username, but we can return just ID)
            # The full URL would be: https://twitter.com/{username}/status/{tweet_id}
            # For now, just return the ID
            tweet_url = f"https://twitter.com/i/web/status/{tweet_id}" if tweet_id else ""

            logging.info(f"[push_x] SUCCESS: Tweet posted with ID {tweet_id}")
            return {
                "success": True,
                "tweet_id": tweet_id,
                "tweet_url": tweet_url
            }
        else:
            error_text = response.text[:500]
            logging.error(f"[push_x] FAILURE: HTTP {response.status_code}")
            logging.error(f"[push_x] Response: {error_text}")
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {error_text[:200]}"
            }

    except Exception as e:
        logging.error(f"[push_x] Exception: {e}")
        return {
            "success": False,
            "error": str(e)
        }
