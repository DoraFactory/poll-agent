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

MAX_HANDLES_PER_SEARCH = 10

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


def _chunk_handles(handles: List[str], size: int) -> List[List[str]]:
    return [handles[i:i + size] for i in range(0, len(handles), size)]


def _score_candidate(poll: dict) -> float:
    stats = poll.get("stats_snapshot") or {}
    try:
        likes = float(stats.get("likes") or 0)
    except (TypeError, ValueError):
        likes = 0.0
    try:
        reposts = float(stats.get("reposts") or 0)
    except (TypeError, ValueError):
        reposts = 0.0
    try:
        replies = float(stats.get("replies") or 0)
    except (TypeError, ValueError):
        replies = 0.0
    try:
        views = float(stats.get("views") or 0)
    except (TypeError, ValueError):
        views = 0.0
    return likes + (2.0 * reposts) + (1.5 * replies) + (views / 1000.0)


def _select_best_candidate_index(
    candidates: List[dict],
    *,
    grok_model: str,
    api_key: Optional[str] = None,
) -> int | None:
    if len(candidates) <= 1:
        return 0 if candidates else None

    shortlist = []
    for idx, item in enumerate(candidates):
        poll = item.get("poll") or {}
        shortlist.append(
            {
                "index": idx,
                "title": poll.get("title"),
                "description": poll.get("description"),
                "options": poll.get("options"),
                "why_choose_this_poll": poll.get("why_choose_this_poll"),
                "stats_snapshot": poll.get("stats_snapshot"),
            }
        )

    prompt = (
        "Select the single best poll candidate. Prefer higher engagement, timeliness, "
        "controversy, and prediction-market relevance. Avoid redundant topics. "
        "Return JSON ONLY as {\"winner_index\": <int>}.\n\n"
        f"Candidates:\n{json.dumps(shortlist)}\n"
    )

    client = Client(api_key=api_key) if api_key else Client()
    chat = client.chat.create(
        model=grok_model,
        temperature=0.0,
        max_tokens=256,
        top_p=1.0,
    )
    chat.append(user(prompt))
    response = chat.sample()
    raw = getattr(response, "content", "")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else {}
        winner = parsed.get("winner_index")
        if isinstance(winner, int) and 0 <= winner < len(candidates):
            return winner
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def _fetch_x_posts_single(
    cleaned_handles: List[str],
    topic_hint: str = "",
    window_seconds: int | None = None,
    *,
    grok_model: str,
    api_key: Optional[str] = None,
    rules_path: str | None = None,
    avoid_round_titles: list[str] | None = None,
    batch_index: int | None = None,
    total_batches: int | None = None,
) -> Dict[str, Any]:
    """Pull recent posts from given handles via Grok x_search and ask Grok
    to propose a poll-worthy topic.
    """
    now_dt = datetime.now(timezone.utc)
    now_utc = now_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    client = Client(api_key=api_key) if api_key else Client()
    batch_label = ""
    if batch_index is not None and total_batches:
        batch_label = f" batch={batch_index + 1}/{total_batches}"
    logging.info(
        "[grok_x_search] chat.create handles=%s window_seconds=%s topic_hint=%s%s",
        cleaned_handles,
        window_seconds,
        topic_hint,
        batch_label,
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

    avoid_block = ""
    if avoid_round_titles:
        lines = "\n".join(f"- {t}" for t in avoid_round_titles[:20] if t and str(t).strip())
        if lines:
            avoid_block = (
                "Recent on-chain poll titles (DO NOT repeat or closely paraphrase; avoid the same core event/person/topic):\n"
                f"{lines}\n\n"
                "Hard constraint: If your best candidate shares the same core subject or event as any title above, "
                "you MUST choose the next-best non-overlapping topic instead.\n\n"
            )
    prompt = (
        f"Current UTC time: {now_utc}. Time window: past {window_label} (~{hours}h).\n\n"
        f"{taget_handles_instructrion}\n\n"
        f"{rules_text}\n\n"
        f"{avoid_block}"
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


def fetch_x_posts(
    handles: List[str],
    topic_hint: str = "",
    window_seconds: int | None = None,
    *,
    grok_model: str,
    api_key: Optional[str] = None,
    rules_path: str | None = None,
    avoid_round_titles: list[str] | None = None,
) -> Dict[str, Any]:
    """Pull recent posts from given handles via Grok x_search and ask Grok
    to propose a poll-worthy topic.
    """
    cleaned_handles = [h.lstrip("@") for h in handles if h.strip()]
    if not cleaned_handles:
        raise ValueError("At least one X handle is required for x_search.")

    if len(cleaned_handles) <= MAX_HANDLES_PER_SEARCH:
        return _fetch_x_posts_single(
            cleaned_handles,
            topic_hint=topic_hint,
            window_seconds=window_seconds,
            grok_model=grok_model,
            api_key=api_key,
            rules_path=rules_path,
            avoid_round_titles=avoid_round_titles,
        )

    batches = _chunk_handles(cleaned_handles, MAX_HANDLES_PER_SEARCH)
    per_handle_batches: List[List[dict]] = []
    candidates: List[dict] = []

    for idx, batch_handles in enumerate(batches):
        result = _fetch_x_posts_single(
            batch_handles,
            topic_hint=topic_hint,
            window_seconds=window_seconds,
            grok_model=grok_model,
            api_key=api_key,
            rules_path=rules_path,
            avoid_round_titles=avoid_round_titles,
            batch_index=idx,
            total_batches=len(batches),
        )
        parsed = result.get("parsed") if isinstance(result, dict) else None
        per_handle: List[dict] = []
        if isinstance(parsed, dict):
            per_handle_value = parsed.get("per_handle")
            if isinstance(per_handle_value, list):
                per_handle = per_handle_value
            poll = parsed.get("poll")
            if poll:
                logging.info(
                    "[grok_x_search] batch %s poll title=%s options=%s",
                    idx + 1,
                    poll.get("title"),
                    poll.get("options"),
                )
                candidates.append({"poll": poll, "batch_index": idx})
            else:
                logging.info("[grok_x_search] batch %s poll none", idx + 1)
        per_handle_batches.append(per_handle)

    winner_index = _select_best_candidate_index(
        candidates,
        grok_model=grok_model,
        api_key=api_key,
    )
    if winner_index is None and candidates:
        winner_index = max(range(len(candidates)), key=lambda i: _score_candidate(candidates[i]["poll"]))

    chosen_poll = None
    winner_batch_index = None
    if winner_index is not None and candidates:
        chosen = candidates[winner_index]
        chosen_poll = chosen.get("poll")
        winner_batch_index = chosen.get("batch_index")

    merged_per_handle: List[dict] = []
    for idx, entries in enumerate(per_handle_batches):
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if winner_batch_index is not None and idx != winner_batch_index:
                if entry.get("status") == "poll_topic_found":
                    entry = {**entry, "status": "no_suitable_topic (reason: selected other batch)"}
            merged_per_handle.append(entry)

    combined = {"per_handle": merged_per_handle, "poll": chosen_poll}
    raw_combined = json.dumps(combined, ensure_ascii=False)
    return {
        "handles": cleaned_handles,
        "prompt": f"combined {len(batches)} batches",
        "raw": raw_combined,
        "parsed": combined,
    }
