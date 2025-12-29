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
    run_once: bool = field(
        default_factory=lambda: os.getenv("RUN_ONCE", "false").lower() in ("true", "1", "yes")
    )
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_chat_ids: List[str] = field(default_factory=lambda: _parse_chat_ids(os.getenv("TELEGRAM_CHAT_IDS")))
    telegram_group_chat_ids: List[str] = field(
        default_factory=lambda: _parse_chat_ids(
            os.getenv("TELEGRAM_GROUP_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_IDS")
        )
    )
    telegram_channel_chat_ids: List[str] = field(
        default_factory=lambda: _parse_chat_ids(os.getenv("TELEGRAM_CHANNEL_CHAT_IDS"))
    )
    # Optional private rules/prompt override (keep the file gitignored and set this env var)
    # Back-compat: X_POLL_PROMPT_PATH is also accepted.
    x_poll_rules_path: str = field(
        default_factory=lambda: os.getenv("X_POLL_RULES_PATH", "") or os.getenv("X_POLL_PROMPT_PATH", "")
    )

    # World MACI API settings
    world_maci_api_endpoint: str = field(default_factory=lambda: os.getenv("WORLD_MACI_API_ENDPOINT", ""))
    world_maci_api_token: str = field(default_factory=lambda: os.getenv("WORLD_MACI_API_TOKEN", ""))
    world_maci_vote_url: str = field(default_factory=lambda: os.getenv("WORLD_MACI_VOTE_URL", ""))
    world_maci_connect_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("WORLD_MACI_CONNECT_TIMEOUT_SECONDS", "10"))
    )
    world_maci_read_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("WORLD_MACI_READ_TIMEOUT_SECONDS", "120"))
    )

    # Dora vota indexer (recent on-chain poll titles, used to avoid duplicates)
    vota_indexer_endpoint: str = field(default_factory=lambda: os.getenv("VOTA_INDEXER_ENDPOINT", ""))
    vota_recent_rounds_n: int = field(default_factory=lambda: int(os.getenv("VOTA_RECENT_ROUNDS_N", "10")))
    vota_indexer_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("VOTA_INDEXER_TIMEOUT_SECONDS", "15"))
    )
    vota_indexer_max_retries: int = field(default_factory=lambda: int(os.getenv("VOTA_INDEXER_MAX_RETRIES", "3")))
    vota_indexer_backoff_seconds: float = field(
        default_factory=lambda: float(os.getenv("VOTA_INDEXER_BACKOFF_SECONDS", "0.5"))
    )
    # Populated at runtime on service start (not from env)
    recent_round_titles: List[str] = field(default_factory=list, init=False, repr=False)

    # Twitter API v2 settings (OAuth 1.0a)
    twitter_api_key: str = field(default_factory=lambda: os.getenv("TWITTER_API_KEY", ""))
    twitter_api_secret: str = field(default_factory=lambda: os.getenv("TWITTER_API_SECRET", ""))
    twitter_access_token: str = field(default_factory=lambda: os.getenv("TWITTER_ACCESS_TOKEN", ""))
    twitter_access_token_secret: str = field(default_factory=lambda: os.getenv("TWITTER_ACCESS_TOKEN_SECRET", ""))

    def require_keys(self) -> None:
        if not self.xai_api_key:
            raise EnvironmentError("Missing XAI_API_KEY in environment or .env file.")
