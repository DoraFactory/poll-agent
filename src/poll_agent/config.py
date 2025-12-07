import os
from dataclasses import dataclass, field
from typing import List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency fallback
    def load_dotenv():
        return None


load_dotenv()


def _parse_handles(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [handle.strip().lstrip("@") for handle in raw.split(",") if handle.strip()]


def _parse_chat_ids(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass
class Settings:
    """Runtime configuration loaded from environment."""

    xai_api_key: str = field(default_factory=lambda: os.getenv("XAI_API_KEY", ""))
    # Model for agents (using Grok via LiteLLM)
    agent_model: str = field(default_factory=lambda: os.getenv("AGENT_MODEL", "grok-beta"))
    # Model for Grok x_search
    grok_model: str = field(default_factory=lambda: os.getenv("GROK_MODEL", "grok-beta"))
    default_handles: List[str] = field(default_factory=lambda: _parse_handles(os.getenv("X_HANDLES")))
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "agents"))
    poll_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("POLL_INTERVAL_SECONDS", "1800"))
    )
    include_trending_news: bool = field(
        default_factory=lambda: os.getenv("INCLUDE_TRENDING_NEWS", "true").lower() in ("true", "1", "yes")
    )
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_chat_ids: List[str] = field(default_factory=lambda: _parse_chat_ids(os.getenv("TELEGRAM_CHAT_IDS")))

    def require_keys(self) -> None:
        if not self.xai_api_key:
            raise EnvironmentError("Missing XAI_API_KEY in environment or .env file.")
