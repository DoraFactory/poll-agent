from __future__ import annotations

from google.adk.agents import Agent
from config import Settings
from tools.grok_x_search import fetch_x_posts


def build_x_feed_agent(settings: Settings) -> Agent:
    """
    Agent dedicated to pulling recent X posts via Grok.

    - grok_recent_posts: 封装 fetch_x_posts，使其成为可被 ADK 调用的工具
    - Agent: 使用 Gemini 模型充当一个数据搬运子代理
    """

    def grok_recent_posts(topic_hint: str = "", max_posts: int = 20) -> dict:
        """
        Fetch recent posts from configured X handles via Grok x_search.

        参数：
        - topic_hint：对主题的提示，用于增强搜索上下文
        - max_posts：限制返回内容数量
        """
        return fetch_x_posts(
            handles=settings.default_handles,
            topic_hint=topic_hint,
            max_posts=max_posts,
            window_seconds=settings.poll_interval_seconds,
            grok_model=settings.grok_model,
            api_key=settings.xai_api_key,
        )

    instruction_text = (
        "你是负责收集并整理 X 平台最新帖子的子代理（x_feed_agent）。\n"
        "你的任务：\n"
        "1. 必须调用 tool `grok_recent_posts` 来获取 X 上的最新内容。\n"
        "2. 收到工具返回后，必须输出工具返回的 'parsed' 字段的完整 JSON 内容。\n"
        "3. 输出格式要求：直接输出 JSON 对象，不要添加任何前缀、后缀、解释或 markdown 代码块。\n"
        "4. 不要修改、重写或生成投票内容，只传递原始数据。\n"
    )

    return Agent(
        name="x_feed_agent",
        model=settings.gemini_model,
        instruction=instruction_text,
        description="Fetches recent posts from configured X handles using Grok search.",
        tools=[grok_recent_posts],
    )