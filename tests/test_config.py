"""Tests for configuration module."""

import pytest
from poll_agent.config import Settings


def test_settings_defaults():
    """Test default settings values."""
    settings = Settings()
    assert settings.agent_model == "grok-beta"
    assert settings.grok_model == "grok-beta"
    assert settings.poll_interval_seconds == 1800
    assert settings.include_trending_news is True
