"""Shared local client-context helpers for reviewed public starter commands."""

from __future__ import annotations

import os
from typing import Any, Mapping

from swarmrepo_sdk import SwarmClient


def resolve_local_byok_context(
    *,
    agent: Mapping[str, Any],
    credentials: Mapping[str, Any],
) -> dict[str, str | None]:
    """Resolve the reviewed local BYOK context from state and environment."""

    provider = (
        str(agent.get("provider") or credentials.get("provider") or os.getenv("EXTERNAL_PROVIDER") or "")
        .strip()
        or None
    )
    model = (
        str(agent.get("model") or credentials.get("model") or os.getenv("EXTERNAL_MODEL") or "")
        .strip()
        or None
    )
    external_api_key = (os.getenv("EXTERNAL_API_KEY") or "").strip() or None
    base_url_override = (
        str(agent.get("base_url") or credentials.get("base_url") or os.getenv("EXTERNAL_BASE_URL") or "")
        .strip()
        or None
    )
    return {
        "provider": provider,
        "model": model,
        "external_api_key": external_api_key,
        "base_url_override": base_url_override,
    }


def apply_local_byok_context(
    client: SwarmClient,
    *,
    agent: Mapping[str, Any],
    credentials: Mapping[str, Any],
) -> dict[str, str | None]:
    """Apply the reviewed local BYOK context to one public SDK client."""

    context = resolve_local_byok_context(agent=agent, credentials=credentials)
    client.set_byok_context(
        provider=context["provider"],
        model=context["model"],
        external_api_key=context["external_api_key"],
        base_url_override=context["base_url_override"],
    )
    return context


__all__ = ["apply_local_byok_context", "resolve_local_byok_context"]
