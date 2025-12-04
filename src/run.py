from __future__ import annotations

import argparse
import sys
from poll_agent.config import Settings
from poll_agent.runner import build_runner
from poll_agent.utils import render_events, to_content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a poll draft from X handles using Grok + Google ADK.",
    )
    parser.add_argument(
        "--handles",
        type=str,
        default="",
        help="Comma separated X handles (without @). Overrides X_HANDLES env.",
    )
    parser.add_argument(
        "--topic-hint",
        type=str,
        default="",
        help="Optional hint for the focus topic (e.g., 'latest product launch').",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=20,
        help="Upper bound of posts to ask Grok to return.",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default="cli-user",
        help="Session user id used by ADK runner.",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default="demo-session",
        help="Session id used by ADK runner.",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="请抓取这些账号的最新帖子并生成一个热门议题投票草案。",
        help="User prompt to feed into the agent.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    settings.require_keys()

    if args.handles:
        settings.default_handles = [h.strip().lstrip("@") for h in args.handles.split(",") if h.strip()]

    if not settings.default_handles:
        print("At least one handle is required (via --handles or X_HANDLES env).", file=sys.stderr)
        return 1

    runner = build_runner(settings)

    user_prompt = (
        f"{args.prompt}\n"
        f"Handles: {', '.join(settings.default_handles)}\n"
        f"If you need data, call grok_recent_posts(topic_hint='{args.topic_hint}', max_posts={args.max_posts})."
    )

    events = runner.run(
        user_id=args.user_id,
        session_id=args.session_id,
        new_message=to_content(user_prompt),
    )
    final_text, tool_calls = render_events(events)

    for call in tool_calls:
        print(f"[tool] {call}")

    print("\n=== Agent Response ===")
    print(final_text or "No response produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
