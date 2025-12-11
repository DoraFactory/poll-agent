from __future__ import annotations

import json
import logging
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

    def grok_recent_posts(topic_hint: str = "") -> dict:
        """
        Fetch recent posts from configured X handles and trending news via Grok x_search.

        Args:
            topic_hint: Topic hint for enhancing search context
            max_posts: Limit the number of returned items
        """
        return fetch_x_posts(
            handles=settings.default_handles,
            topic_hint=topic_hint,
            window_seconds=settings.poll_interval_seconds,
            grok_model=settings.grok_model,
            api_key=settings.xai_api_key,
        )

    instruction_text = (
        "You are the x_feed_agent responsible for collecting and organizing recent X posts" +
        (" and trending news.\n" if settings.include_trending_news else ".\n") +
        "Your tasks:\n"
        f"1. Call the `grok_recent_posts` tool to fetch latest posts from configured X handles only:\n"
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
        include_contents=None,
        instruction=instruction_text,
        description="Fetches recent posts from configured X handles using Grok search.",
        tools=[grok_recent_posts],
    )