"""Push poll data to World MACI API endpoint."""

from __future__ import annotations

import logging
import hashlib
import time
from typing import Dict, Any

from poll_agent.monitoring import log_metric

try:
    import requests
    from requests import exceptions as _requests_exceptions
except ImportError:
    requests = None


def push_poll_to_chain(
    poll_title: str,
    poll_description: str,
    voting_options: list[str],
    api_endpoint: str,
    api_token: str,
    vercel_automation_bypass_secret: str = "",
    *,
    connect_timeout_seconds: float = 10.0,
    read_timeout_seconds: float = 120.0,
) -> Dict[str, Any]:
    """
    Push poll data to World MACI API endpoint and get contract address.

    Args:
        poll_title: The poll question/title
        poll_description: Detailed description of the poll
        voting_options: List of voting options
        api_endpoint: World MACI API endpoint URL
        api_token: Bearer token for authentication

    Returns:
        dict with 'success' (bool), 'contract_address' (str if success), 'error' (str if failed)
    """
    logging.info("[push_chain] push_poll_to_chain called")
    logging.info(f"[push_chain] title: {poll_title}, options: {voting_options}")
    logging.info("[push_chain] vercel_bypass_enabled=%s", bool(vercel_automation_bypass_secret))

    if not api_endpoint:
        return {
            "success": False,
            "error": "World MACI API endpoint not configured"
        }

    if not api_token:
        return {
            "success": False,
            "error": "World MACI API token not configured"
        }

    if requests is None:
        return {
            "success": False,
            "error": "requests library not available"
        }

    try:
        idempotency_key = hashlib.sha256(
            f"{poll_title}\n{poll_description}\n{voting_options}".encode("utf-8")
        ).hexdigest()
        headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
            # Safe to send even if server doesn't support it; helps prevent duplicates if it does.
            'Idempotency-Key': idempotency_key,
        }
        if vercel_automation_bypass_secret:
            headers['x-vercel-protection-bypass'] = vercel_automation_bypass_secret

        start = time.time()
        response = requests.post(
            api_endpoint,
            headers=headers,
            json={
                'pollTitle': poll_title,
                'pollDescription': poll_description,
                'votingOptions': voting_options,
            },
            timeout=(connect_timeout_seconds, read_timeout_seconds),
        )

        duration = round(time.time() - start, 3)

        # Accept both 200 (OK) and 201 (Created) as success
        if response.status_code in [200, 201]:
            result = response.json()
            if result.get('success'):
                contract_address = result.get('data', {}).get('contractAddress', '')
                logging.info(f"[push_chain] SUCCESS: Poll created on chain with HTTP {response.status_code}")
                logging.info(f"[push_chain] Contract address: {contract_address}")
                log_metric(
                    "poll_agent.world_maci.push_chain",
                    success=True,
                    http_status=response.status_code,
                    duration_seconds=duration,
                    contract_address=contract_address,
                    title=poll_title[:160],
                )
                return {
                    "success": True,
                    "contract_address": contract_address
                }
            else:
                error_msg = result.get('error', {}).get('message', 'Unknown error')
                logging.error(f"[push_chain] FAILURE: API returned success=false - {error_msg}")
                log_metric(
                    "poll_agent.world_maci.push_chain",
                    success=False,
                    http_status=response.status_code,
                    duration_seconds=duration,
                    error=error_msg[:300],
                    title=poll_title[:160],
                )
                return {
                    "success": False,
                    "error": f"API error: {error_msg}"
                }
        else:
            logging.error(f"[push_chain] FAILURE: HTTP error {response.status_code}")
            logging.error(f"[push_chain] Response: {response.text[:500]}")
            log_metric(
                "poll_agent.world_maci.push_chain",
                success=False,
                http_status=response.status_code,
                duration_seconds=duration,
                error=(response.text or "")[:300],
                title=poll_title[:160],
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }

    except _requests_exceptions.ReadTimeout as e:
        # Server may have completed the action but responded slowly.
        logging.error(
            "[push_chain] Read timeout after connect=%ss read=%ss: %s",
            connect_timeout_seconds,
            read_timeout_seconds,
            e,
        )
        log_metric(
            "poll_agent.world_maci.push_chain",
            success=False,
            maybe_success=True,
            error=str(e)[:300],
            title=poll_title[:160],
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
        )
        return {
            "success": False,
            "error": f"World MACI API read timeout (connect={connect_timeout_seconds}s read={read_timeout_seconds}s): {e}",
            "maybe_success": True,
        }
    except Exception as e:
        logging.error(f"[push_chain] Exception: {e}")
        log_metric(
            "poll_agent.world_maci.push_chain",
            success=False,
            error=str(e)[:300],
            title=poll_title[:160],
        )
        return {
            "success": False,
            "error": str(e)
        }
