from __future__ import annotations

# Google Agent Development Kit
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

# Your internal modules
from agent import build_poll_orchestrator
from config import Settings
from x_agent.agent import build_x_feed_agent


def build_runner(settings: Settings) -> Runner:
    """
    Create the ADK runner composed of source-specific agents.

    - x_agent: 负责从 X（通过 Grok / X Search）获取内容的 agent
    - orchestrator: Poll orchestration agent，用于汇总结果并生成投票
    """

    # 子 Agent：负责 X 数据（可能是 Grok Search Agent）
    x_agent = build_x_feed_agent(settings)

    # 协调器 Agent：负责 orchestrating poll generation
    orchestrator = build_poll_orchestrator(settings, sub_agents=[x_agent])

    # 会话管理，简单使用内存实现
    session_service = InMemorySessionService()

    # 最终返回 ADK Runner
    return Runner(
        app_name=settings.app_name,
        agent=orchestrator,
        session_service=session_service,
    )