from __future__ import annotations

from google.adk.agents import Agent

from poll_agent.config import Settings
from poll_agent.tools.grok_x_search import fetch_x_posts


def build_x_feed_agent(settings: Settings) -> Agent:
    """Agent dedicated to pulling recent X posts via Grok."""

    def grok_recent_posts(topic_hint: str = "", max_posts: int = 20) -> dict:
        """Fetch recent posts from configured X handles via Grok x_search."""
        return fetch_x_posts(
            handles=settings.default_handles,
            topic_hint=topic_hint,
            max_posts=max_posts,
            grok_model=settings.grok_model,
            api_key=settings.xai_api_key,
        )

    return Agent(
        name="x_feed_agent",
        model=settings.gemini_model,
        instruction=(
            "你是负责收集 X 平台最新帖子的数据代理。"
            "步骤：1) 必须调用 `grok_recent_posts` 获取帖子。"
            "2) 将结果整理为简洁 JSON，字段包含 handle、posted_at、url、engagement、text。"
            "不要生成投票或讨论，只返回数据（必要时可以附上简短摘要）。"
        ),
        description="Fetches recent posts from configured X handles using Grok search.",
        tools=[grok_recent_posts],
    )
