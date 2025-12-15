"""Telegram messaging utilities for sending poll results."""

from __future__ import annotations

import logging
from typing import List

from poll_agent.monitoring import log_metric

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


def send_telegram_message(
    message: str,
    telegram_token: str,
    chat_ids: List[str],
) -> dict:
    """
    Send a message to specified Telegram chat IDs.

    Args:
        message: The message text to send
        telegram_token: Telegram bot token
        chat_ids: List of chat IDs to send the message to

    Returns:
        dict with 'success' (bool) and 'details' (list of per-chat results)
    """
    logging.info("[telegram] send_telegram_message called")
    logging.info(f"[telegram] message length: {len(message)}, chat_ids: {chat_ids}")

    if not telegram_token:
        log_metric("poll_agent.telegram.send_message", success=False, error="missing_token")
        return {
            "success": False,
            "error": "TELEGRAM_TOKEN not configured",
            "details": []
        }

    if not chat_ids:
        log_metric("poll_agent.telegram.send_message", success=False, error="missing_chat_ids")
        return {
            "success": False,
            "error": "No chat IDs provided",
            "details": []
        }

    if requests is None:
        log_metric("poll_agent.telegram.send_message", success=False, error="requests_missing")
        return {
            "success": False,
            "error": "requests library not available",
            "details": []
        }

    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    results = []
    success_count = 0

    logging.info(f"[telegram] Will send to {len([c for c in chat_ids if c])} chat(s)")

    for chat_id in chat_ids:
        if not chat_id:
            continue

        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"  # Use HTML instead of Markdown for better reliability
        }

        try:
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                logging.info(f"[telegram] Message sent to chat_id {chat_id}")
                results.append({
                    "chat_id": chat_id,
                    "success": True
                })
                success_count += 1
            else:
                logging.warning(
                    f"[telegram] Failed to send to {chat_id}: {response.status_code} {response.text}"
                )
                results.append({
                    "chat_id": chat_id,
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                })
        except Exception as e:
            logging.error(f"[telegram] Error sending to {chat_id}: {e}")
            results.append({
                "chat_id": chat_id,
                "success": False,
                "error": str(e)
            })

    result = {
        "success": success_count > 0,
        "sent_count": success_count,
        "total_chats": len([c for c in chat_ids if c]),
        "details": results
    }

    log_metric(
        "poll_agent.telegram.send_message",
        success=result["success"],
        sent_count=result["sent_count"],
        total_chats=result["total_chats"],
    )
    logging.info(f"[telegram] send_telegram_message completed: success={result['success']}, sent={success_count}")
    return result
