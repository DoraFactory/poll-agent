from __future__ import annotations

from typing import List
from google.adk.agents import Agent

from config import Settings


def build_poll_orchestrator(settings: Settings, sub_agents: List[Agent]) -> Agent:
    """
    Root agent that delegates to source-specific agents then crafts a poll.

    - 子代理（如 x_agent）负责从 X / Grok 获取 poll 数据
    - 本 orchestrator 负责最终汇总并生成投票草案
    """

    instruction_text = (
        "你是投票策划的主代理（Poll Orchestrator）。"
        "工作流程：先调用子代理（如 x_agent）获取 poll 数据，然后必须输出 JSON，总是有内容，禁止空响应。\n"
        "内容政策：几乎所有话题都允许（政治、选举、战争、宗教、争议话题等），"
        "仅拒绝直接煽动暴力、露骨色情、泄露隐私的内容。"
        "选项必须保持中立、对称、客观、<=20字。\n"
        "输出格式（必须输出）：\n"
        "{\n"
        "  per_handle_status: 子代理返回的每个 handle 的 status 列表（照搬即可）；\n"
        "  poll_interval_posts_list: 如有可用帖子则列出概要，否则可为空数组；\n"
        "  poll: {topic_title, rationale(3-5句), poll_question, options(2-4个<=20字且对称中立), sample_posts(2-4条,含handle+简述), handles_covered} 或 null;\n"
        "  explain: 若 poll 为 null，必须填原因（如“窗口内无新帖”或“敏感/不合规”）。\n"
        "}\n"
        "即使没有合规话题，也要输出上述 JSON，poll 置 null 并写明 explain。保持事实，不编造。"
    )

    return Agent(
        name="poll_orchestrator",
        model=settings.gemini_model,
        instruction=instruction_text,
        description="Orchestrates sub-agents and synthesizes poll draft.",
        sub_agents=sub_agents,
    )
