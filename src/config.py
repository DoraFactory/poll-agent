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


@dataclass
class Settings:
    """Runtime configuration loaded from environment."""

    google_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    xai_api_key: str = field(default_factory=lambda: os.getenv("XAI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-pro"))
    grok_model: str = field(default_factory=lambda: os.getenv("GROK_MODEL", "grok-4-1-fast"))
    default_handles: List[str] = field(default_factory=lambda: _parse_handles(os.getenv("X_HANDLES")))
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "agents"))
    poll_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("POLL_INTERVAL_SECONDS", "1800"))
    )

    def require_keys(self) -> None:
        if not self.google_api_key:
            raise EnvironmentError("Missing GOOGLE_API_KEY in environment or .env file.")
        if not self.xai_api_key:
            raise EnvironmentError("Missing XAI_API_KEY in environment or .env file.")
