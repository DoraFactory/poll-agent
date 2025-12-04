from __future__ import annotations

from typing import List

from google.adk.agents import Agent

from poll_agent.config import Settings


def build_poll_orchestrator(settings: Settings, sub_agents: List[Agent]) -> Agent:
    """Root agent that delegates to source-specific agents then crafts a poll."""

    return Agent(
        name="poll_orchestrator",
        model=settings.gemini_model,
        instruction=(
            "你是投票策划的主代理。请根据可用的子代理提供的数据来生成一个热门议题投票草案。"
            "流程：先委派合适的子代理获取数据（例如 x_feed_agent 负责 X 帖子）。"
            "收到数据后，提炼最热主题并输出 JSON："
            "topic_title, rationale(3-5句), poll_question, options(2-4个简短选项), "
            "sample_posts(2-4条引用，带 handle 与摘要), handles_covered。"
            "保持客观中立，不编造信息；如果数据为空或不足，提供 explain 字段说明原因。"
        ),
        description="Orchestrates sub-agents and synthesizes poll draft.",
        sub_agents=sub_agents,
    )
