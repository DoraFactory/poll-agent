from __future__ import annotations

import json
from typing import Any

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from poll_agent.config import Settings
from poll_agent.tools.grok_x_search import fetch_x_posts


def build_x_feed_agent(settings: Settings) -> Agent:
    """
    Agent dedicated to pulling recent X posts via Grok.

    - grok_recent_posts: Wraps fetch_x_posts to make it callable by ADK
    - Agent: Uses Gemini model as a data-fetching sub-agent
    """

    def _decorate_per_handle(entries: Any, source_group: str) -> list[dict]:
        if not isinstance(entries, list):
            return []
        decorated: list[dict] = []
        for entry in entries:
            if isinstance(entry, dict):
                decorated.append({**entry, "source_group": source_group})
        return decorated

    def _decorate_poll(poll: Any, source_group: str, force_tag: str | None = None) -> dict | None:
        if not isinstance(poll, dict):
            return None
        decorated = {**poll, "source_group": source_group}
        if force_tag:
            decorated["tag"] = force_tag
            decorated["category"] = force_tag
        return decorated

    def grok_recent_posts(topic_hint: str = "") -> dict:
        """
        Fetch recent posts from configured X handles and trending news via Grok x_search.

        Args:
            topic_hint: Topic hint for enhancing search context
            max_posts: Limit the number of returned items
        """
        x_per_handle: list[dict] = []
        x_poll: dict | None = None
        if settings.default_handles:
            x_result = fetch_x_posts(
                handles=settings.default_handles,
                topic_hint=topic_hint,
                window_seconds=settings.poll_interval_seconds,
                grok_model=settings.grok_model,
                api_key=settings.xai_api_key,
                rules_path=settings.x_poll_rules_path or None,
                avoid_round_titles=settings.recent_round_titles or None,
            )
            x_parsed = x_result.get("parsed") if isinstance(x_result, dict) else None
            x_per_handle = _decorate_per_handle(
                x_parsed.get("per_handle") if isinstance(x_parsed, dict) else [],
                "X_HANDLES",
            )
            x_poll = _decorate_poll(
                x_parsed.get("poll") if isinstance(x_parsed, dict) else None,
                "X_HANDLES",
            )

        private_per_handle: list[dict] = []
        private_poll: dict | None = None
        if settings.private_wires:
            private_result = fetch_x_posts(
                handles=settings.private_wires,
                topic_hint=topic_hint,
                window_seconds=settings.poll_interval_seconds,
                grok_model=settings.grok_model,
                api_key=settings.xai_api_key,
                rules_path=settings.x_poll_rules_path or None,
                avoid_round_titles=settings.recent_round_titles or None,
            )
            private_parsed = private_result.get("parsed") if isinstance(private_result, dict) else None
            private_per_handle = _decorate_per_handle(
                private_parsed.get("per_handle") if isinstance(private_parsed, dict) else [],
                "PRIVATE_WIRES",
            )
            private_poll = _decorate_poll(
                private_parsed.get("poll") if isinstance(private_parsed, dict) else None,
                "PRIVATE_WIRES",
                force_tag="PRIVATE_WIRES",
            )

        polls = [poll for poll in [x_poll, private_poll] if poll]
        primary_per_handle = x_per_handle if x_per_handle else private_per_handle
        primary_poll = x_poll if x_poll else private_poll
        combined = {
            "per_handle": primary_per_handle,
            "poll": primary_poll,
            "private_wires_per_handle": private_per_handle,
            "private_wires_poll": private_poll,
            "polls": polls,
            "sources": [
                {
                    "source_group": "X_HANDLES",
                    "handles": settings.default_handles,
                    "per_handle": x_per_handle,
                    "poll": x_poll,
                },
                {
                    "source_group": "PRIVATE_WIRES",
                    "handles": settings.private_wires,
                    "per_handle": private_per_handle,
                    "poll": private_poll,
                },
            ],
        }
        settings.latest_x_feed_payload = combined
        raw_combined = json.dumps(combined, ensure_ascii=False)
        return {
            "handles": {
                "X_HANDLES": settings.default_handles,
                "PRIVATE_WIRES": settings.private_wires,
            },
            "prompt": "combined X_HANDLES and PRIVATE_WIRES",
            "raw": raw_combined,
            "parsed": combined,
        }

    instruction_text = (
        "You are the x_feed_agent responsible for collecting and organizing recent X posts" +
        (" and trending news.\n" if settings.include_trending_news else ".\n") +
        "Your tasks:\n"
        "1. Call the `grok_recent_posts` tool to fetch latest posts from both source groups:\n"
        "   - X_HANDLES (regular source list)\n"
        "   - PRIVATE_WIRES (private source list)\n"
        "2. Extract the JSON string from the 'raw' field in the tool response.\n"
        "3. Output the JSON directly without any modifications, markdown blocks, or explanations.\n"
    )

    # Use LiteLlm to load Grok model
    # LiteLlm uses OpenAI-compatible format for xAI
    import os
    os.environ["XAI_API_KEY"] = settings.xai_api_key

    grok_llm = LiteLlm(
        model=f"xai/{settings.agent_model}",
    )

    return Agent(
        name="x_feed_agent",
        model=grok_llm,
        include_contents='none',
        instruction=instruction_text,
        description="Fetches recent posts from X_HANDLES and PRIVATE_WIRES using Grok search.",
        tools=[grok_recent_posts],
    )
