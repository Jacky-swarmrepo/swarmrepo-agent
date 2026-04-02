"""Explicit agent registration command for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from typing import Any, Mapping

from swarmrepo_sdk import DEFAULT_SWARM_REPO_URL, SwarmClient, SwarmSDKError
from swarmrepo_agent_runtime.agent_naming import (
    build_retry_agent_name,
    resolve_configured_agent_name,
)
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

from ._version import __version__
from .legal_context import resolve_reviewed_legal_context
from .legal_evidence import build_current_agent_legal_evidence_summary
from .legal_state import build_reviewed_legal_state, save_reviewed_legal_state
from .status_remote import load_remote_legal_state
from .status_summary import (
    build_agent_summary,
    build_auth_summary,
    build_endpoint_summary,
    build_legal_summary,
    build_state_checks,
)


DEFAULT_AGENT_NAME_REGISTRATION_ATTEMPTS = 4


def _required_value(value: str | None, *, env_name: str, field_label: str) -> str:
    normalized = str(value or "").strip()
    if normalized:
        return normalized
    raise RuntimeError(f"Configuration error: missing {field_label}. Set {env_name}.")


def _credentials_payload(
    *,
    existing_credentials: Mapping[str, Any],
    registration: Any,
    agent_name: str,
    provider: str,
    model: str,
    base_url_override: str | None,
    saved_at: str,
) -> dict[str, Any]:
    payload = dict(existing_credentials)
    payload.update(
        {
            "access_token": registration.access_token,
            "refresh_token": getattr(registration, "refresh_token", None),
            "access_token_expires_at": (
                registration.expires_at.isoformat()
                if getattr(registration, "expires_at", None) is not None
                else None
            ),
            "refresh_token_expires_at": (
                registration.refresh_expires_at.isoformat()
                if getattr(registration, "refresh_expires_at", None) is not None
                else None
            ),
            "agent_name": agent_name,
            "provider": provider,
            "model": model,
            "base_url": base_url_override,
            "owner_id": str(registration.owner_id),
            "saved_at": saved_at,
        }
    )
    return payload


def _agent_payload(*, registration: Any, saved_at: str) -> dict[str, Any]:
    return {
        "agent_id": str(registration.agent.id),
        "agent_name": registration.agent.name,
        "provider": registration.agent.provider,
        "model": registration.agent.model,
        "base_url": registration.agent.base_url,
        "merged_count": registration.agent.merged_count,
        "created_at": registration.agent.created_at.isoformat(),
        "owner_id": str(registration.owner_id),
        "saved_at": saved_at,
    }


def _workflow_navigation() -> dict[str, Any]:
    return {
        "workflow_phase": "ready_for_ai_workflows",
        "next_step_commands": [
            {
                "command": "swarmrepo-agent auth whoami --json",
                "reason": "Confirm the newly registered remote identity and legal context.",
            },
            {
                "command": "swarmrepo-agent status legal --json",
                "reason": "Inspect the authenticated remote legal evidence summary for the registered agent.",
            },
            {
                "command": "swarmrepo-agent repo create --name demo-repo --language python",
                "reason": "Create the first reviewed repository container for this starter identity.",
            },
            {
                "command": 'swarmrepo-agent pr request-ai --repo-id <repo-id> --prompt "Fix the parser crash."',
                "reason": "Delegate one reviewed AI change request after a repository exists.",
            },
        ],
    }


def _render_register_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    data = payload.get("data") or {}
    legal_summary = data.get("legal_summary") or {}
    agent_summary = data.get("agent_summary") or {}
    auth_summary = data.get("auth_summary") or {}

    evidence_complete = legal_summary.get("evidence_complete")
    if evidence_complete is True:
        evidence_label = "complete"
    elif evidence_complete is False:
        evidence_label = "partial"
    else:
        evidence_label = "(local only)"

    print("SwarmRepo agent registration:")
    print("- state: registered ready")
    print(f"- agent: {agent_summary.get('agent_name') or '(missing)'}")
    print(
        "- principal: "
        f"{legal_summary.get('accepted_by_principal_type') or '(unknown)'} / "
        f"{legal_summary.get('accepted_by_principal_id') or '(unknown)'}"
    )
    print(
        "- refresh token: "
        f"{'present' if auth_summary.get('refresh_token_present') else '(missing)'}"
    )
    print(f"- legal evidence: {evidence_label}")
    print(f"- state dir: {payload.get('state_dir') or '(unknown)'}")

    for hint in (data.get("workflow_navigation") or {}).get("next_step_commands") or []:
        command = hint.get("command")
        if command:
            print(f"Next: {command}")

    for warning in payload.get("warnings") or []:
        print(f"warning: {warning}")


async def _register_agent_with_retry(
    client: SwarmClient,
    *,
    agent_name: str,
    generated_agent_name: bool,
    external_api_key: str,
    provider: str,
    model: str,
    base_url_override: str | None,
    registration_grant: str,
) -> tuple[Any, str]:
    pending_agent_name = agent_name
    last_error: SwarmSDKError | None = None

    for _ in range(DEFAULT_AGENT_NAME_REGISTRATION_ATTEMPTS):
        try:
            registration = await client.register_agent(
                agent_name=pending_agent_name,
                external_api_key=external_api_key,
                provider=provider,
                model=model,
                base_url=base_url_override,
                registration_grant=registration_grant,
            )
            return registration, pending_agent_name
        except SwarmSDKError as exc:
            if (
                not generated_agent_name
                or exc.status_code != 409
                or "already registered" not in str(exc).lower()
            ):
                raise
            last_error = exc
            pending_agent_name = build_retry_agent_name(provider)

    raise last_error or RuntimeError("Unable to register the reviewed starter.")


async def _agent_register_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    resolved_state_dir = resolve_state_dir(args.state_dir or os.getenv("AGENT_STATE_DIR"))
    rendered_state_dir = str(display_state_dir(resolved_state_dir))
    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")

    provider = _required_value(
        args.provider or os.getenv("EXTERNAL_PROVIDER"),
        env_name="EXTERNAL_PROVIDER",
        field_label="provider",
    )
    external_api_key = _required_value(
        args.external_api_key or os.getenv("EXTERNAL_API_KEY"),
        env_name="EXTERNAL_API_KEY",
        field_label="external API key",
    )
    model = _required_value(
        args.model or os.getenv("EXTERNAL_MODEL"),
        env_name="EXTERNAL_MODEL",
        field_label="model",
    )
    base_url_override = str(args.external_base_url or os.getenv("EXTERNAL_BASE_URL") or "").strip() or None
    requested_agent_name = str(args.agent_name or "").strip()
    agent_name, generated_agent_name = (
        (requested_agent_name, False)
        if requested_agent_name
        else resolve_configured_agent_name(provider)
    )

    remote_legal_state: dict[str, Any] | None = None
    remote_legal_error: dict[str, str] | None = None
    warnings: list[str] = []

    with acquire_state_lock(resolved_state_dir):
        credentials = load_state_document(credentials_path(resolved_state_dir))
        existing_legal = load_state_document(legal_state_path(resolved_state_dir))
        existing_agent = load_state_document(agent_state_path(resolved_state_dir))
        if credentials.get("access_token") or existing_agent.get("agent_id"):
            raise RuntimeError(
                "Registration aborted: this state directory already contains a registered agent. "
                "Use a new --state-dir for explicit registration."
            )

        legal_context = resolve_reviewed_legal_context(
            legal_state=existing_legal,
            default_client_kind="swarmrepo_agent",
            default_client_version=__version__,
        )
        registration_grant = str(
            args.registration_grant or existing_legal.get("registration_grant") or ""
        ).strip()
        if not registration_grant:
            raise RuntimeError(
                "Registration requires a reviewed registration grant. "
                "Run `swarmrepo-agent legal accept --yes --json` first."
            )

        async with SwarmClient(base_url=base_url, **legal_context.client_kwargs()) as client:
            registration, final_agent_name = await _register_agent_with_retry(
                client,
                agent_name=agent_name,
                generated_agent_name=generated_agent_name,
                external_api_key=external_api_key,
                provider=provider,
                model=model,
                base_url_override=base_url_override,
                registration_grant=registration_grant,
            )
            if not registration.access_token:
                raise RuntimeError("Registration did not return an access token.")
            remote_legal_state, remote_legal_error = await load_remote_legal_state(
                base_url=base_url,
                access_token=registration.access_token,
            )

        if remote_legal_error is not None:
            warnings.append(
                "Remote legal-state validation did not succeed. agent register is using local legal state."
            )

        saved_at = datetime.now(timezone.utc).isoformat()
        updated_credentials = _credentials_payload(
            existing_credentials=credentials,
            registration=registration,
            agent_name=final_agent_name,
            provider=provider,
            model=model,
            base_url_override=base_url_override,
            saved_at=saved_at,
        )
        updated_agent = _agent_payload(registration=registration, saved_at=saved_at)
        updated_legal = build_reviewed_legal_state(
            existing_legal,
            legal_context=legal_context,
            registration_grant_consumed=(
                True
                if getattr(registration, "registration_grant_consumed", None) is None
                else bool(registration.registration_grant_consumed)
            ),
            legal_binding_summary=getattr(registration, "legal_binding_summary", None),
            saved_at=saved_at,
        )
        save_state_document(credentials_path(resolved_state_dir), updated_credentials)
        save_state_document(agent_state_path(resolved_state_dir), updated_agent)
        save_reviewed_legal_state(str(resolved_state_dir), updated_legal)

    auth_summary = build_auth_summary(updated_credentials)
    legal_summary = build_legal_summary(updated_legal, remote_legal_state=remote_legal_state)
    agent_summary = build_agent_summary(updated_agent)
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
        "command": "agent register",
        "state_dir": rendered_state_dir,
        "data": {
            "registration_state": "registered_ready",
            "registration_grant_source": (
                "argument"
                if str(args.registration_grant or "").strip()
                else "local_state"
            ),
            "auth_summary": auth_summary,
            "legal_summary": legal_summary,
            "legal_binding_summary": updated_legal.get("legal_binding_summary"),
            "agent_summary": agent_summary,
            "endpoint_summary": endpoint_summary,
            "state_checks": state_checks,
            "workflow_navigation": _workflow_navigation(),
            "current_agent_legal_evidence_summary": build_current_agent_legal_evidence_summary(
                remote_legal_state
            ),
            "remote_legal_error": dict(remote_legal_error) if remote_legal_error else None,
        },
        "warnings": warnings,
    }
    _render_register_payload(payload, as_json=bool(args.json))
    return 0


def agent_register_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent agent register`."""

    try:
        return asyncio.run(_agent_register_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(format_user_facing_error(exc))
        return 1


__all__ = ["agent_register_command"]
