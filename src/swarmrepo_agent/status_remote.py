"""Remote helper reads for the reviewed public starter status commands."""

from __future__ import annotations

from typing import Any

from swarmrepo_sdk import SwarmClient, SwarmSDKError


async def load_remote_legal_state(
    *,
    base_url: str,
    access_token: str | None,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """Load the current agent's authenticated legal state via bearer auth only."""
    if not access_token:
        return None, None

    try:
        async with SwarmClient(base_url=base_url, access_token=access_token) as client:
            payload = await client.get_me_legal_state()
    except (OSError, SwarmSDKError) as exc:
        return None, {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }

    return payload.model_dump(mode="json"), None


__all__ = ["load_remote_legal_state"]
