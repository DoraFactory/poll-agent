from __future__ import annotations

import os
from typing import Any, Dict

from poll_agent.main import main


def handler(event: Any = None, context: Any = None) -> Dict[str, Any]:
    """
    AWS Lambda entrypoint.

    Configure the function with environment variables
    (XAI_API_KEY, X_HANDLES, PRIVATE_WIRES, etc.).
    Set RUN_ONCE=true (defaulted here) so the agent runs a single iteration and exits.
    """
    os.environ.setdefault("RUN_ONCE", "true")

    exit_code = main()
    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
    }
