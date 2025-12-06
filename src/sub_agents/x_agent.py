from __future__ import annotations

from google.adk.agents import Agent
from config import Settings
from tools.grok_x_search import fetch_x_posts


def build_x_feed_agent(settings: Settings) -> Agent:
    """
    Agent dedicated to pulling recent X posts via Grok.

    - grok_recent_posts: Wraps fetch_x_posts to make it callable by ADK
    - Agent: Uses Gemini model as a data-fetching sub-agent
    """

    def grok_recent_posts(topic_hint: str = "", max_posts: int = 20) -> dict:
        """
        Fetch recent posts from configured X handles and trending news via Grok x_search.

        Args:
            topic_hint: Topic hint for enhancing search context
            max_posts: Limit the number of returned items
        """
        return fetch_x_posts(
            handles=settings.default_handles,
            topic_hint=topic_hint,
            max_posts=max_posts,
            window_seconds=settings.poll_interval_seconds,
            include_trending_news=settings.include_trending_news,
            grok_model=settings.grok_model,
            api_key=settings.xai_api_key,
        )

    news_hint = ""
    if settings.include_trending_news:
        news_hint = (
            "   - Latest posts from configured X handles\n"
            "   - Trending topics on X/Twitter platform (X's trending section, viral posts)\n"
            "   - Breaking news tweets on X related to politics, prediction markets, technology\n"
            "   NOTE: Only use content from X/Twitter platform, NOT from external websites\n"
        )
    else:
        news_hint = "   - Latest posts from configured X handles only\n"

    instruction_text = (
        "You are the x_feed_agent responsible for collecting and organizing recent X posts" +
        (" and trending news.\n" if settings.include_trending_news else ".\n") +
        "Your tasks:\n"
        f"1. MUST call the `grok_recent_posts` tool to fetch:\n"
        f"{news_hint}"
        "2. After receiving tool response, output the complete JSON content from the 'parsed' field.\n"
        "3. Output format requirement: Output JSON directly, no prefixes, suffixes, explanations, or markdown code blocks.\n"
        "4. Do not modify, rewrite, or generate poll content. Only pass through the raw data.\n"
    )

    return Agent(
        name="x_feed_agent",
        model=settings.gemini_model,
        instruction=instruction_text,
        description="Fetches recent posts from configured X handles using Grok search.",
        tools=[grok_recent_posts],
    )