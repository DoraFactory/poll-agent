from __future__ import annotations

import logging
import random
import time
from typing import List

try:
    import requests
    from requests import exceptions as _requests_exceptions
except ImportError:  # pragma: no cover
    requests = None


def fetch_recent_round_titles(
    *,
    endpoint: str,
    n: int = 10,
    timeout_seconds: float = 15.0,
    max_retries: int = 3,
    backoff_seconds: float = 0.5,
) -> List[str]:
    """
    Fetch latest on-chain poll (round) titles from Dora vota indexer GraphQL API.
    """
    if not endpoint:
        raise ValueError("Missing indexer endpoint")
    if n <= 0:
        return []
    if requests is None:
        raise RuntimeError("requests library not available")

    query = "query($n:Int!){ rounds(first:$n, orderBy: TIMESTAMP_DESC){ nodes{ roundTitle } } }"
    max_retries = max(1, int(max_retries))
    last_exc: BaseException | None = None
    payload: dict = {}

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                endpoint,
                headers={"content-type": "application/json"},
                json={"query": query, "variables": {"n": int(n)}},
                timeout=timeout_seconds,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Indexer HTTP {resp.status_code}: {resp.text[:200]}")

            payload = resp.json() if resp.content else {}
            last_exc = None
            break
        except (_requests_exceptions.RequestException, ValueError, RuntimeError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            sleep_seconds = backoff_seconds * (2 ** (attempt - 1))
            sleep_seconds += random.random() * min(0.25, sleep_seconds)
            logging.warning(
                "[vota_indexer] attempt %s/%s failed: %s; retrying in %.2fs",
                attempt,
                max_retries,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    if last_exc is not None:
        raise last_exc

    nodes = (((payload.get("data") or {}).get("rounds") or {}).get("nodes") or [])
    titles: List[str] = []
    for node in nodes:
        title = (node or {}).get("roundTitle")
        if not title:
            continue
        title = str(title).strip()
        if title and title not in titles:
            titles.append(title)

    logging.info("[vota_indexer] fetched recent titles=%s", len(titles))
    logging.info("[vota_indexer] titles: %s", titles)
    return titles
