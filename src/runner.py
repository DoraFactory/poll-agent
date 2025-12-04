from __future__ import annotations

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

from poll_agent.agents.poll_orchestrator import build_poll_orchestrator
from poll_agent.agents.x_feed_agent import build_x_feed_agent
from poll_agent.config import Settings


def build_runner(settings: Settings) -> Runner:
    """Create the ADK runner composed of source-specific agents."""
    x_agent = build_x_feed_agent(settings)
    orchestrator = build_poll_orchestrator(settings, sub_agents=[x_agent])

    session_service = InMemorySessionService()
    return Runner(
        app_name=settings.app_name,
        agent=orchestrator,
        session_service=session_service,
    )
