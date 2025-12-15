"""Small wrapper around xai-sdk `x_search` to pull recent X posts for handles."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search

from poll_agent.monitoring import log_metric


def _load_x_poll_rules_text(rules_path: str | None) -> str:
    if rules_path:
        with open(rules_path, "r", encoding="utf-8") as f:
            return f.read()

    for base in Path(__file__).resolve().parents:
        default_path = base / "prompts" / "x_poll_rules.txt"
        if default_path.exists():
            return default_path.read_text(encoding="utf-8")

    raise RuntimeError(
        "Unable to load poll rules text from prompts/x_poll_rules.txt. "
        "Create that file or set X_POLL_RULES_PATH to a readable rules file."
    )


def fetch_x_posts(
    handles: List[str],
    topic_hint: str = "",
    window_seconds: int | None = None,
    *,
    grok_model: str,
    api_key: Optional[str] = None,
    rules_path: str | None = None,
) -> Dict[str, Any]:
    """Pull recent posts from given handles via Grok x_search and ask Grok
    to propose a poll-worthy topic.
    """
    cleaned_handles = [h.lstrip("@") for h in handles if h.strip()]
    if not cleaned_handles:
        raise ValueError("At least one X handle is required for x_search.")

    now_dt = datetime.now(timezone.utc)
    now_utc = now_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    client = Client(api_key=api_key) if api_key else Client()
    logging.info(
        "[grok_x_search] chat.create handles=%s window_seconds=%s topic_hint=%s",
        cleaned_handles,
        window_seconds,
        topic_hint,
    )
    # Configure x_search - by default it only searches X/Twitter platform
    # Enable image understanding to analyze images in posts
    chat = client.chat.create(
        model=grok_model,
        tools=[
            x_search(
                allowed_x_handles=cleaned_handles,
                enable_image_understanding=True,
            ),
        ],
        temperature=0.0,
        max_tokens=4096,
        top_p=1.0,
    )

    hours = round(window_seconds / 3600, 2) if window_seconds else "recent"
    window_label = f"{window_seconds} seconds" if window_seconds else "recent window"
    handles_str = ", ".join(cleaned_handles)
    taget_handles_instructrion = f"Target handles: {handles_str}"

    json_example = """
{
  "per_handle": [
    {
      "handle": "elonmusk",
      "status": "poll_topic_found" | "no_new_posts_in_window" | "no_suitable_topic (reason: xxx)",
      "post_count": 5
    }
  ],
  "poll": {
    "title": "Should/Will the US implement universal basic income? (Use smart quotes "" and Will/Should appropriately)",
    "description": "According to recent policy discussions, there are growing debates about implementing a universal basic income program. Proponents argue it could reduce poverty, while critics cite concerns about fiscal sustainability. The proposal has gained traction across multiple political groups. (Use smart quotes "" and apostrophes ' throughout)",
    "options": [
      "Yes",
      "No"
    ],
    "sample_posts": [{"handle": "elonmusk", "summary": "brief description", "url": "https://x.com/..."}],
    "why_choose_this_poll": "Explain why THIS topic was selected over others: high engagement, controversy, timeliness, prediction market relevance, etc.",
    "stats_snapshot": {"likes": 0, "reposts": 0, "replies": 0, "views": 0}
  }
}
"""

    rules_text = _load_x_poll_rules_text(rules_path).strip()
    prompt = (
        f"Current UTC time: {now_utc}. Time window: past {window_label} (~{hours}h).\n\n"
        f"{taget_handles_instructrion}\n\n"
        f"{rules_text}\n\n"
        "Output STRICTLY the following JSON (JSON ONLY, no explanations, no ```json wrapper):\n"
        f"{json_example.strip()}\n\n"
        "- Execute now.\n"
    )
    chat.append(user(prompt))

    logging.info("[grok_x_search] calling chat.sample ...")
    t0 = time.time()
    response = chat.sample()
    duration = round(time.time() - t0, 3)
    raw_content = getattr(response, "content", "")
    logging.info(
        "[grok_x_search] sample done, raw type=%s length=%s",
        type(raw_content),
        len(raw_content) if hasattr(raw_content, "__len__") else "n/a",
    )
    log_metric(
        "poll_agent.grok_x_search.sample",
        success=isinstance(raw_content, str),
        duration_seconds=duration,
        window_seconds=window_seconds,
        handles=len(cleaned_handles),
        raw_length=len(raw_content) if isinstance(raw_content, str) else None,
    )
    parsed = json.loads(raw_content) if isinstance(raw_content, str) else raw_content

    return {
        "handles": cleaned_handles,
        "prompt": prompt,
        "raw": raw_content,
        "parsed": parsed,
    }
