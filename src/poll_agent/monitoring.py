from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict


def _utc_now_iso() -> str:
    # Example: 2025-12-15T02:03:04Z
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_metric(name: str, **fields: Any) -> None:
    """
    Emit a single-line JSON metric suitable for log-based alerting.

    CloudWatch Logs / GKE Logging can turn these into metrics via filters.
    """
    payload: Dict[str, Any] = {
        "ts": _utc_now_iso(),
        "metric": name,
        **fields,
    }
    logging.info("METRIC %s", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
