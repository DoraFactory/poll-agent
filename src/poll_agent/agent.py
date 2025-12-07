from __future__ import annotations

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

from poll_agent.config import Settings
from poll_agent.sub_agents.x_agent import build_x_feed_agent
from poll_agent.sub_agents.tg_agent import build_telegram_agent


def build_runner(settings: Settings) -> Runner:
    """
    Create the ADK runner with a sequential agent pipeline.

    Pipeline:
    1. x_feed_agent: Fetches recent posts from X handles using Grok
    2. telegram_agent: Sends the generated poll data to Telegram

    Returns:
        Runner: Configured ADK Runner ready to process requests
    """

    # Build sub-agents
    x_agent = build_x_feed_agent(settings)
    telegram_agent = build_telegram_agent(settings)

    # Create sequential orchestrator
    description_text = (
        "A two-step pipeline for poll generation and notification:\n"
        "1. x_feed_agent: Fetches recent posts from X handles using Grok\n"
        "2. telegram_agent: Sends the generated poll data to Telegram\n\n"
        "Output the final poll JSON in the format: "
        "{per_handle: [...], poll_interval_posts_list: [...], poll: {...} or null, explain: ...}\n\n"
        "Content policy: Allow politics, elections, war, religion, controversial topics. "
        "Only reject direct violence incitement, explicit pornography, privacy leaks. "
        "Options must be neutral, balanced, objective, <=20 chars."
    )

    orchestrator = SequentialAgent(
        name="poll_orchestrator",
        description=description_text,
        sub_agents=[x_agent, telegram_agent],
    )

    # Create session service
    session_service = InMemorySessionService()

    # Return configured runner
    return Runner(
        app_name=settings.app_name,
        agent=orchestrator,
        session_service=session_service,
    )
