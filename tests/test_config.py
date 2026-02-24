"""Tests for configuration module."""

from poll_agent.config import Settings


def test_settings_defaults(monkeypatch):
    """Test default settings values."""
    monkeypatch.delenv("X_HANDLES", raising=False)
    monkeypatch.delenv("PRIVATE_WIRES", raising=False)
    monkeypatch.delenv("VERCEL_AUTOMATION_BYPASS_SECRET", raising=False)
    settings = Settings()
    assert settings.agent_model == "grok-beta"
    assert settings.grok_model == "grok-beta"
    assert settings.poll_interval_seconds == 1800
    assert settings.include_trending_news is True
    assert settings.default_handles == []
    assert settings.private_wires == []
    assert settings.vercel_automation_bypass_secret == ""


def test_private_wires_parse(monkeypatch):
    monkeypatch.setenv("X_HANDLES", "alice, @bob")
    monkeypatch.setenv("PRIVATE_WIRES", "wire_1, @wire_2")
    monkeypatch.setenv("VERCEL_AUTOMATION_BYPASS_SECRET", "bypass-secret")
    settings = Settings()
    assert settings.default_handles == ["alice", "bob"]
    assert settings.private_wires == ["wire_1", "wire_2"]
    assert settings.vercel_automation_bypass_secret == "bypass-secret"
