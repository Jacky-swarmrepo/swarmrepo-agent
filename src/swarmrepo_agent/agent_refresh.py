"""Credential refresh command for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from typing import Any, Mapping

from swarmrepo_sdk import DEFAULT_SWARM_REPO_URL, SwarmClient, SwarmSDKError
from swarmrepo_agent_runtime.env import load_reviewed_dotenv
from swarmrepo_agent_runtime.state import (
    acquire_state_lock,
    agent_state_path,
    credentials_path,
    display_state_dir,
    legal_state_path,
    load_state_document,
    resolve_state_dir,
    save_state_document,
)
from swarmrepo_agent_runtime.user_errors import format_user_facing_error

from .status_summary import (
    build_agent_summary,
    build_auth_summary,
    build_endpoint_summary,
    build_legal_summary,
    build_state_checks,
)


def _workflow_navigation() -> dict[str, Any]:
    return {
        "workflow_phase": "ready_for_ai_workflows",
        "next_step_commands": [
            {
                "command": "swarmrepo-agent auth whoami --json",
                "reason": "Validate the refreshed access token against the hosted identity surface.",
            },
            {
                "command": "swarmrepo-agent status auth --json",
                "reason": "Inspect the rotated local credential timestamps and refresh-token readiness.",
            },
            {
                "command": "swarmrepo-agent status legal --json",
                "reason": "Confirm the current authenticated legal summary when needed.",
            },
        ],
    }


def _refresh_summary_payload(refresh_result: Any) -> dict[str, Any]:
    expires_at = getattr(refresh_result, "expires_at", None)
    refresh_expires_at = getattr(refresh_result, "refresh_expires_at", None)
    return {
        "rotation_id": (
            str(refresh_result.rotation_id)
            if getattr(refresh_result, "rotation_id", None) is not None
            else None
        ),
        "access_token_expires_at": expires_at.isoformat() if expires_at is not None else None,
        "refresh_token_expires_at": (
            refresh_expires_at.isoformat() if refresh_expires_at is not None else None
        ),
    }


def _updated_credentials_payload(
    existing_credentials: Mapping[str, Any],
    *,
    refresh_result: Any,
    saved_at: str,
) -> dict[str, Any]:
    payload = dict(existing_credentials)
    payload.update(
        {
            "access_token": refresh_result.access_token,
            "refresh_token": refresh_result.refresh_token,
            "access_token_expires_at": (
                refresh_result.expires_at.isoformat()
                if getattr(refresh_result, "expires_at", None) is not None
                else None
            ),
            "refresh_token_expires_at": (
                refresh_result.refresh_expires_at.isoformat()
                if getattr(refresh_result, "refresh_expires_at", None) is not None
                else None
            ),
            "rotation_id": (
                str(refresh_result.rotation_id)
                if getattr(refresh_result, "rotation_id", None) is not None
                else None
            ),
            "saved_at": saved_at,
            "last_refresh_at": saved_at,
        }
    )
    return payload


def _updated_legal_payload(
    existing_legal: Mapping[str, Any],
    *,
    refresh_result: Any,
    saved_at: str,
) -> dict[str, Any]:
    payload = dict(existing_legal)
    legal_binding_summary = getattr(refresh_result, "legal_binding_summary", None)
    if legal_binding_summary is None:
        if payload:
            payload["saved_at"] = saved_at
        return payload

    if hasattr(legal_binding_summary, "model_dump"):
        binding_payload = legal_binding_summary.model_dump(mode="json")
    else:
        binding_payload = dict(legal_binding_summary)

    payload.update(binding_payload)
    payload["saved_at"] = saved_at
    return payload


def _render_refresh_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    data = payload.get("data") or {}
    agent_summary = data.get("agent_summary") or {}
    refresh_summary = data.get("refresh_summary") or {}
    state_dir = payload.get("state_dir") or "(unknown)"
    workflow_navigation = data.get("workflow_navigation") or {}

    print("SwarmRepo credential refresh:")
    print("- state: refreshed ready")
    print(f"- agent: {agent_summary.get('agent_name') or '(missing)'}")
    print(
        "- access token expires at: "
        f"{refresh_summary.get('access_token_expires_at') or '(unknown)'}"
    )
    print(
        "- refresh token expires at: "
        f"{refresh_summary.get('refresh_token_expires_at') or '(unknown)'}"
    )
    print(f"- rotation id: {refresh_summary.get('rotation_id') or '(unknown)'}")
    print(f"- state dir: {state_dir}")

    for hint in workflow_navigation.get("next_step_commands") or []:
        command = hint.get("command")
        if command:
            print(f"Next: {command}")

    for warning in payload.get("warnings") or []:
        print(f"warning: {warning}")


async def _agent_refresh_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    resolved_state_dir = resolve_state_dir(args.state_dir or os.getenv("AGENT_STATE_DIR"))
    rendered_state_dir = str(display_state_dir(resolved_state_dir))
    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")

    with acquire_state_lock(resolved_state_dir):
        credentials = load_state_document(credentials_path(resolved_state_dir))
        legal = load_state_document(legal_state_path(resolved_state_dir))
        agent = load_state_document(agent_state_path(resolved_state_dir))
        refresh_token = str(credentials.get("refresh_token") or "").strip()
        if not refresh_token:
            raise RuntimeError(
                "No stored refresh token is available. Run `swarmrepo-agent agent onboard --yes` first."
            )

        async with SwarmClient(base_url=base_url) as client:
            refresh_result = await client.refresh_access_token(refresh_token=refresh_token)

        saved_at = datetime.now(timezone.utc).isoformat()
        updated_credentials = _updated_credentials_payload(
            credentials,
            refresh_result=refresh_result,
            saved_at=saved_at,
        )
        updated_legal = _updated_legal_payload(
            legal,
            refresh_result=refresh_result,
            saved_at=saved_at,
        )
        save_state_document(credentials_path(resolved_state_dir), updated_credentials)
        if updated_legal:
            save_state_document(legal_state_path(resolved_state_dir), updated_legal)

    auth_summary = build_auth_summary(updated_credentials)
    legal_summary = build_legal_summary(updated_legal)
    agent_summary = build_agent_summary(agent)
    endpoint_summary = build_endpoint_summary(
        base_url=base_url,
        state_dir=rendered_state_dir,
    )
    state_checks = build_state_checks(
        auth_summary=auth_summary,
        legal_summary=legal_summary,
        agent_summary=agent_summary,
    )
    payload = {
        "command": "agent refresh",
        "state_dir": rendered_state_dir,
        "data": {
            "refresh_state": "refreshed_ready",
            "refresh_summary": _refresh_summary_payload(refresh_result),
            "auth_summary": auth_summary,
            "legal_summary": legal_summary,
            "agent_summary": agent_summary,
            "endpoint_summary": endpoint_summary,
            "state_checks": state_checks,
            "workflow_navigation": _workflow_navigation(),
        },
        "warnings": [],
    }
    _render_refresh_payload(payload, as_json=bool(args.json))
    return 0


def agent_refresh_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent agent refresh`."""

    try:
        return asyncio.run(_agent_refresh_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(format_user_facing_error(exc))
        return 1


__all__ = ["agent_refresh_command"]
