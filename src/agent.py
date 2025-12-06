from __future__ import annotations

from typing import List
from google.adk.agents import Agent

from config import Settings


def build_poll_orchestrator(settings: Settings, sub_agents: List[Agent]) -> Agent:
    """
    Root agent that delegates to source-specific agents then crafts a poll.

    - 子代理（如 x_agent）负责从 X / Grok 获取 poll 数据
    - 子代理（telegram_agent）负责发送结果到 Telegram
    - 本 orchestrator 负责协调整个流程
    """

    instruction_text = (
        "你是投票策划和通知的主代理（Poll Orchestrator）。\n"
        "你的核心职责：收集 X 数据、生成投票、发送 Telegram 通知。\n\n"
        "【工作流程 - 必须全部完成】：\n\n"
        "第一阶段：数据收集\n"
        "→ 调用 x_feed_agent 获取 X 平台数据\n"
        "→ 分析返回的数据\n\n"
        "第二阶段：生成投票\n"
        "→ 根据数据构建投票 JSON（包含 per_handle_status, poll, explain 等）\n\n"
        "第三阶段：发送通知（这一步绝对不能省略！）\n"
        "→ 调用 telegram_agent\n"
        "→ 将构建好的 JSON 传递给它\n"
        "→ 等待发送完成的确认\n\n"
        "第四阶段：输出结果\n"
        "→ 输出最终的 JSON\n\n"
        "【检查清单】在输出结果前，确认你已经：\n"
        "☐ 调用了 x_feed_agent？\n"
        "☐ 调用了 telegram_agent？\n"
        "☐ 收到了 Telegram 发送确认？\n"
        "→ 如果三个都打钩了，才能输出 JSON\n\n"
        "内容政策：允许政治、选举、战争、宗教、争议话题，"
        "仅拒绝煽动暴力、露骨色情、泄露隐私。选项需中立对称，<=20字。\n\n"
        "最终输出格式：{per_handle_status, poll_interval_posts_list, poll, explain}"
    )

    return Agent(
        name="poll_orchestrator",
        model=settings.gemini_model,
        instruction=instruction_text,
        description="Orchestrates sub-agents and synthesizes poll draft.",
        sub_agents=sub_agents,
    )
