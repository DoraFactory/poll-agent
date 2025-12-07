"""Small wrapper around xai-sdk `x_search` to pull recent X posts for handles."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from xai_sdk import Client
from xai_sdk.chat import user
from xai_sdk.tools import x_search


def fetch_x_posts(
    handles: List[str],
    topic_hint: str = "",
    max_posts: int = 20,
    window_seconds: int | None = None,
    include_trending_news: bool = True,
    *,
    grok_model: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Pull recent posts from given handles via Grok x_search and ask Grok
    to propose a poll-worthy topic.
    """
    cleaned_handles = [h.lstrip("@") for h in handles if h.strip()]
    if not cleaned_handles:
        raise ValueError("At least one X handle is required for x_search.")

    now_dt = datetime.now(timezone.utc)
    now_utc = now_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    since_iso = (
        (now_dt - timedelta(seconds=window_seconds)).isoformat()
        if window_seconds
        else None
    )

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

    news_instruction = ""
    if include_trending_news:
        news_instruction = f"""
Additionally, search for trending news and hot topics on X (Twitter) platform within the same time window. Combine insights from:
1. Posts from specified handles: {handles_str}
2. Trending topics on X/Twitter (check X's trending section, viral posts, breaking news tweets)
3. Popular discussions on X related to politics, prediction markets, technology, or current events

IMPORTANT: Only use content from X/Twitter platform. Do NOT include content from external websites, blogs, or news sites.
Select the SINGLE most poll-worthy topic across ALL X sources (handles + X trending topics)."""
    else:
        news_instruction = f"Target handles: {handles_str}"

    prompt = f"""
Current UTC time: {now_utc}. Time window: past {window_label} (~{hours}h).

{news_instruction}

For each handle, collect all posts/replies/retweets. Analyze engagement metrics (likes, replies, reposts, views) and trending signals to select the single most poll-worthy topic.

Core Requirements:
1. Almost all topics are allowed: politics, elections, war, religion, controversial topics, prediction markets, etc.
2. Technology, economy, society, entertainment, sports, culture and all mainstream topics are allowed
3. Maintain objectivity and neutrality: titles and options must be balanced with no obvious bias, options ≤20 words, EXACTLY 2 options only.

Only Reject These:
- Direct incitement to violence/harm
- Explicit pornographic content
- Privacy leaks (public figures' public info is acceptable)

Optional topic hint: {topic_hint or 'none'}

Output STRICTLY the following JSON (JSON ONLY, no explanations, no ```json wrapper):
{{
  "per_handle": [
    {{
      "handle": "elonmusk",
      "status": "poll_topic_found" | "no_new_posts_in_window" | "no_suitable_topic (reason: xxx)",
      "poll_interval_posts_list": [
        {{
          "handle": "elonmusk",
          "posted_at": "YYYY-MM-DDTHH:MM:SSZ",
          "url": "https://x.com/...",
          "engagement": {{"likes": 0, "reposts": 0, "quotes": 0, "replies": 0, "views": 0}},
          "context_summary": "1-2 sentences explaining why this is noteworthy",
          "is_reply": false,
          "in_reply_to_url": "",
          "is_retweet": false,
          "original_url": "",
          "text": "full original text"
        }}
      ],
      "poll": {{
        "title": "Engaging question that captures the topic (e.g., 'Will Europe cut bureaucracy by 2026?')",
        "description": "2-3 sentences describing what happened. CRITICAL: Use NEUTRAL reporting language - 'According to reports...', 'Sources indicate...', 'There are claims that...', 'It has been reported that...'. DO NOT state unverified claims as facts. Focus on the EVENT itself, NOT who posted it. Do NOT mention account names, handles, engagement metrics (likes/reposts/views), or posting statistics.",
        "options": [
          "Option A (≤20 words, neutral)",
          "Option B (≤20 words, neutral)"
        ],
        "sample_posts": [{{ "handle": "elonmusk", "summary": "brief description", "url": "https://x.com/..." }}],
        "why_choose_this_poll": "Explain why THIS topic was selected over others: high engagement, controversy, timeliness, prediction market relevance, etc.",
        "stats_snapshot": {{ "likes": 0, "reposts": 0, "replies": 0, "views": 0 }}
      }}
    }}
  ]
}}

Rules:
- Collect all posts from all handles in the time window first, then select the single most poll-worthy topic; don't output other topics.
- Political and prediction market topics MUST be prioritized, do NOT self-censor.
- If no new posts or violates core rejection rules, poll MUST be null, keep only "handle" and "status" fields.
- Maximum ONE poll object per time window.
- You MUST output pure JSON ONLY, NO prefixes, suffixes, explanations, markdown, ```json wrapper, apologies, or reminders.
- Do NOT reject content just because it involves politics. Political topics are fully allowed.

Poll Field Requirements:
- "title": MUST be an engaging question that makes people want to vote. Should be clear, direct, and thought-provoking.
- "description": Describe the EVENT/NEWS in 2-3 sentences using NEUTRAL, OBJECTIVE language:
  * Use phrases like: "According to reports...", "Sources claim...", "There are allegations that...", "It has been reported that..."
  * DO NOT state unverified claims as absolute facts
  * Focus ONLY on what happened and why it matters
  * DO NOT mention who posted it, account names, or engagement numbers (likes/reposts/views)
  * Write like a neutral news agency reporting on claims, not endorsing them
- "why_choose_this_poll": Explain the competitive advantage of this topic - why it beat other candidates (engagement metrics, controversy level, timeliness, prediction market potential, public interest).

- Execute now.
"""
    chat.append(user(prompt))

    logging.info("[grok_x_search] calling chat.sample ...")
    response = chat.sample()
    raw_content = getattr(response, "content", "")
    logging.info(
        "[grok_x_search] sample done, raw type=%s length=%s",
        type(raw_content),
        len(raw_content) if hasattr(raw_content, "__len__") else "n/a",
    )
    parsed = json.loads(raw_content) if isinstance(raw_content, str) else raw_content

    return {
        "handles": cleaned_handles,
        "prompt": prompt,
        "raw": raw_content,
        "parsed": parsed,
    }
