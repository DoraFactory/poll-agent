"""Small wrapper around xai-sdk `x_search` to pull recent X posts for handles."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search


def fetch_x_posts(
    handles: List[str],
    topic_hint: str = "",
    max_posts: int = 20,
    *,
    grok_model: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Pull recent posts from given handles via Grok x_search.

    The function asks Grok to return concise JSON so the downstream agent can
    reason over the posts deterministically.
    """
    cleaned_handles = [h.lstrip("@") for h in handles if h.strip()]
    if not cleaned_handles:
        raise ValueError("At least one X handle is required for x_search.")

    client = Client(api_key=api_key) if api_key else Client()
    chat = client.chat.create(
        model=grok_model,
        tools=[
            x_search(allowed_x_handles=cleaned_handles),
        ],
    )

    prompt = (
        "Use x_search to fetch the most recent posts from these handles and "
        f"return a JSON array with at most {max_posts} items. Each item should "
        "include: handle, posted_at (ISO8601 if available), url, engagement "
        "(reposts/likes if available), and text. "
        f"Handles: {', '.join(cleaned_handles)}. "
        f"Optional topic hint: {topic_hint or 'none'}."
    )
    chat.append(user(prompt))

    # Prefer a single non-streaming turn to keep the tool synchronous.
    response = chat.sample()
    raw_content = getattr(response, "content", "")
    parsed = None
    if isinstance(raw_content, str):
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            parsed = None

    return {
        "handles": cleaned_handles,
        "prompt": prompt,
        "raw": raw_content,
        "parsed": parsed,
        "citations": getattr(response, "citations", None),
    }
