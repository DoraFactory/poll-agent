from __future__ import annotations

import json
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
                tool_summaries.append(
                    f"tool_call: {call.name} args={_safe_json_for_log(_sanitize_for_log(args))}"
                )
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


_REDACT_KEYS = {"poll_data", "message", "prompt", "raw", "parsed"}
_MAX_STRING_LEN = 320
_MAX_LIST_ITEMS = 8
_MAX_DICT_ITEMS = 16
_MAX_DEPTH = 4


def _safe_json_for_log(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return repr(value)


def _truncate_string(value: str) -> str:
    if len(value) <= _MAX_STRING_LEN:
        return value
    return f"{value[:_MAX_STRING_LEN]}…<truncated len={len(value)}>"


def _sanitize_for_log(value, *, _depth: int = 0, _key: str | None = None):
    if _key in _REDACT_KEYS:
        if isinstance(value, str):
            return f"<redacted len={len(value)}>"
        return "<redacted>"

    if _depth >= _MAX_DEPTH:
        return "<truncated depth>"

    if value is None:
        return None

    if isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        return _truncate_string(value)

    if isinstance(value, bytes):
        return f"<bytes len={len(value)}>"

    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= _MAX_DICT_ITEMS:
                out["<truncated>"] = f"<dict items={len(value)}>"
                break
            key_str = str(k)
            out[key_str] = _sanitize_for_log(v, _depth=_depth + 1, _key=key_str)
        return out

    if isinstance(value, (list, tuple)):
        items = []
        for i, v in enumerate(value):
            if i >= _MAX_LIST_ITEMS:
                items.append(f"<truncated items={len(value)}>")
                break
            items.append(_sanitize_for_log(v, _depth=_depth + 1, _key=_key))
        return items

    return _truncate_string(repr(value))
