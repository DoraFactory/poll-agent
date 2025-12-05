from __future__ import annotations

from typing import Iterable, List, Tuple

from google.genai import types


def to_content(user_message: str) -> types.Content:
    """Utility to turn a string into a Content object for Runner.run."""
    return types.Content(
        role="user",
        parts=[types.Part(text=user_message)],
    )


def render_events(events: Iterable) -> Tuple[str, List[str]]:
    """Extract the final response text and any tool call logs for CLI output."""
    final_text = ""
    tool_summaries: List[str] = []
    last_text = ""
    for event in events:
        calls = getattr(event, "get_function_calls", lambda: [])()
        if calls:
            for call in calls:
                args = getattr(call, "args", None) or getattr(call, "arguments", None)
                tool_summaries.append(f"tool_call: {call.name} args={args}")
        text = _content_to_text(getattr(event, "content", None))
        if text:
            last_text = text
        if getattr(event, "is_final_response", lambda: False)():
            final_text = text
    if not final_text:
        final_text = last_text
    return final_text, tool_summaries


def _content_to_text(content: types.Content | None) -> str:
    if not content or not getattr(content, "parts", None):
        return ""
    texts = []
    for part in content.parts:
        if part.text:
            texts.append(part.text)
    return "\n".join(texts)
