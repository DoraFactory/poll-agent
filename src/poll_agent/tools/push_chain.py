"""Push poll data to World MACI API endpoint."""

from __future__ import annotations

import logging
from typing import Dict, Any

try:
    import requests
except ImportError:
    requests = None


def push_poll_to_chain(
    poll_title: str,
    poll_description: str,
    voting_options: list[str],
    api_endpoint: str,
    api_token: str,
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
        response = requests.post(
            api_endpoint,
            headers={
                'Authorization': f'Bearer {api_token}',
                'Content-Type': 'application/json',
            },
            json={
                'pollTitle': poll_title,
                'pollDescription': poll_description,
                'votingOptions': voting_options,
            },
            timeout=30
        )

        # Accept both 200 (OK) and 201 (Created) as success
        if response.status_code in [200, 201]:
            result = response.json()
            if result.get('success'):
                contract_address = result.get('data', {}).get('contractAddress', '')
                logging.info(f"[push_chain] SUCCESS: Poll created on chain with HTTP {response.status_code}")
                logging.info(f"[push_chain] Contract address: {contract_address}")
                return {
                    "success": True,
                    "contract_address": contract_address
                }
            else:
                error_msg = result.get('error', {}).get('message', 'Unknown error')
                logging.error(f"[push_chain] FAILURE: API returned success=false - {error_msg}")
                return {
                    "success": False,
                    "error": f"API error: {error_msg}"
                }
        else:
            logging.error(f"[push_chain] FAILURE: HTTP error {response.status_code}")
            logging.error(f"[push_chain] Response: {response.text[:500]}")
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }

    except Exception as e:
        logging.error(f"[push_chain] Exception: {e}")
        return {
            "success": False,
            "error": str(e)
        }