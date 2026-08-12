"""
Async HTTP client for the notification/ops services this side of the
estate calls.

DELIBERATE DEFECT (planted for the code analyzer's secretsFindings[]):
NOTIFICATION_API_KEY is read from the environment, but falls back to a
hardcoded literal when unset. This is the one planted hardcoded credential
in the Python service -- everything else here reads secrets from the
environment only.
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_FALLBACK_API_KEY = "nwb_notify_sk_9d2f7a1c8e0b4356"


def _api_key() -> str:
    key = os.environ.get("NOTIFICATION_API_KEY")
    if not key:
        logger.warning("NOTIFICATION_API_KEY not set -- falling back to embedded key")
        return _FALLBACK_API_KEY
    return key


async def post_json(url: str, payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url, json=payload, headers={"Authorization": f"Bearer {_api_key()}"}
            )
            logger.info("POST %s -> %s", url, response.status_code)
            return response.status_code < 300
    except httpx.HTTPError:
        # The reference app has no live external endpoints to call --
        # simulate success rather than fail every seeded instance on a
        # DNS/connection error to a fictional internal host.
        logger.info("POST %s (simulated -- no live endpoint in this environment)", url)
        return True


async def get_json(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {_api_key()}"})
            logger.info("GET %s -> %s", url, response.status_code)
            return response.json() if response.status_code < 300 else {}
    except httpx.HTTPError:
        logger.info("GET %s (simulated -- no live endpoint in this environment)", url)
        return {}
