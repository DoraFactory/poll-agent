from __future__ import annotations

import json
import logging
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from config import Settings
from tools.grok_x_search import fetch_x_posts


def build_x_feed_agent(settings: Settings) -> Agent:
    """
    Agent dedicated to pulling recent X posts via Grok.

    - grok_recent_posts: Wraps fetch_x_posts to make it callable by ADK
    - Agent: Uses Gemini model as a data-fetching sub-agent
    """

    def grok_recent_posts(topic_hint: str = "", max_posts: int = 20) -> dict:
        """
        Fetch recent posts from configured X handles and trending news via Grok x_search.

        Args:
            topic_hint: Topic hint for enhancing search context
            max_posts: Limit the number of returned items
        """
        return fetch_x_posts(
            handles=settings.default_handles,
            topic_hint=topic_hint,
            max_posts=max_posts,
            window_seconds=settings.poll_interval_seconds,
            include_trending_news=settings.include_trending_news,
            grok_model=settings.grok_model,
            api_key=settings.xai_api_key,
        )

    def validate_and_fix_json(json_string: str) -> dict:
        """
        Validate and fix common JSON formatting issues.

        Args:
            json_string: The JSON string to validate and fix

        Returns:
            dict with 'valid' (bool), 'fixed_json' (str), and 'errors' (list)
        """
        logging.info("[x_agent] validate_and_fix_json called")
        errors = []
        fixed = json_string.strip()

        # Remove markdown code blocks
        if fixed.startswith("```"):
            lines = fixed.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
                errors.append("Removed opening markdown code block")
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
                errors.append("Removed closing markdown code block")
            fixed = '\n'.join(lines)

        # Fix escaped single quotes (invalid in JSON)
        if "\\'" in fixed:
            fixed = fixed.replace("\\'", "'")
            errors.append("Fixed escaped single quotes")

        # Fix Python-style booleans
        if "False" in fixed or "True" in fixed:
            fixed = fixed.replace("False", "false").replace("True", "true")
            errors.append("Fixed Python-style booleans")

        # Try to parse
        try:
            json.loads(fixed)
            logging.info(f"[x_agent] JSON validation successful, {len(errors)} fixes applied")
            return {
                "valid": True,
                "fixed_json": fixed,
                "errors": errors if errors else ["No errors found"]
            }
        except json.JSONDecodeError as e:
            logging.error(f"[x_agent] JSON validation failed: {e}")
            return {
                "valid": False,
                "fixed_json": fixed,
                "errors": errors + [f"JSON parse error: {str(e)}"]
            }

    news_hint = ""
    if settings.include_trending_news:
        news_hint = (
            "   - Latest posts from configured X handles\n"
            "   - Trending topics on X/Twitter platform (X's trending section, viral posts)\n"
            "   - Breaking news tweets on X related to politics, prediction markets, technology\n"
            "   NOTE: Only use content from X/Twitter platform, NOT from external websites\n"
        )
    else:
        news_hint = "   - Latest posts from configured X handles only\n"

    instruction_text = (
        "You are the x_feed_agent responsible for collecting and organizing recent X posts" +
        (" and trending news.\n" if settings.include_trending_news else ".\n") +
        "Your tasks:\n"
        f"1. Call the `grok_recent_posts` tool to fetch:\n"
        f"{news_hint}"
        "2. Extract the JSON string from the 'raw' field in the tool response.\n"
        "3. Output the JSON directly without any modifications, markdown blocks, or explanations.\n"
    )

    # Use LiteLlm to load Grok model
    # LiteLlm uses OpenAI-compatible format for xAI
    import os
    os.environ["XAI_API_KEY"] = settings.xai_api_key

    grok_llm = LiteLlm(
        model=f"xai/{settings.agent_model}",
    )

    return Agent(
        name="x_feed_agent",
        model=grok_llm,
        instruction=instruction_text,
        description="Fetches recent posts from configured X handles using Grok search.",
        tools=[grok_recent_posts],
    )