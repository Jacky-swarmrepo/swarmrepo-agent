"""Status commands for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from textwrap import dedent
from typing import Any

from swarmrepo_sdk import DEFAULT_SWARM_REPO_URL, SwarmSDKError

from swarmrepo_agent_runtime.env import load_reviewed_dotenv
from swarmrepo_agent_runtime.state import (
    agent_state_path,
    credentials_path,
    display_state_dir,
    legal_state_path,
    load_state_document,
    resolve_state_dir,
)
from swarmrepo_agent_runtime.user_errors import format_user_facing_error

from .legal_evidence import build_current_agent_legal_evidence_summary
from .status_remote import load_remote_legal_state
from .status_summary import (
    build_agent_summary,
    build_auth_summary,
    build_endpoint_summary,
    build_legal_summary,
    build_overview,
    build_state_checks,
    build_workflow_navigation,
)


def register_status_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register the reviewed starter status commands."""

    status_parser = subparsers.add_parser(
        "status",
        help="Inspect local starter state, readiness checks, and remote legal evidence summaries.",
        description=dedent(
            """\
            Inspect reviewed starter state.

            Available sections:
            - `status` shows the overview plus next-step workflow guidance
            - `status legal` shows the accepted terms summary and remote legal evidence when available
            - `status auth` shows token presence and local credential storage
            - `status agent` shows the current starter-local agent identity snapshot

            `status legal` prefers the authenticated remote legal-state summary
            when a local access token and reachable API base URL are available.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent status
              swarmrepo-agent status legal --json
              swarmrepo-agent status auth
              swarmrepo-agent status agent
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status_parser.add_argument(
        "section",
        nargs="?",
        choices=["legal", "auth", "agent"],
        help="Optional status section: legal, auth, or agent.",
    )
    status_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    status_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for remote legal-state reads.",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the status payload as JSON.",
    )
    status_parser.set_defaults(handler=status_command)


def _render_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    warnings = payload.get("warnings") or []
    data = payload.get("data") or {}
    command = payload.get("command")
    resolved_state_dir = payload.get("state_dir") or "(unknown)"
    endpoint_summary = data.get("endpoint_summary") or {}
    workflow_navigation = data.get("workflow_navigation") or {}

    workflow_phase = workflow_navigation.get("workflow_phase") or "(unknown)"

    def _render_next_steps() -> None:
        for hint in workflow_navigation.get("next_step_commands") or []:
            next_command = hint.get("command")
            if next_command:
                print(f"Next: {next_command}")

    if command == "status auth":
        auth_summary = data.get("auth_summary") or {}
        access_token_status = (
            "expired"
            if auth_summary.get("access_token_expired") is True
            else ("present" if auth_summary.get("access_token_present") else "missing")
        )
        refresh_token_status = (
            "expired"
            if auth_summary.get("refresh_token_expired") is True
            else ("present" if auth_summary.get("refresh_token_present") else "missing")
        )
        print("Authentication summary:")
        print(f"- access token: {access_token_status}")
        print(f"- refresh token: {refresh_token_status}")
        if auth_summary.get("access_token_expires_at"):
            print(f"- access token expires at: {auth_summary.get('access_token_expires_at')}")
        if auth_summary.get("refresh_token_expires_at"):
            print(f"- refresh token expires at: {auth_summary.get('refresh_token_expires_at')}")
        print(
            f"- refresh token storage: {auth_summary.get('refresh_token_storage') or '(unknown)'}"
        )
        print(f"- endpoint: {endpoint_summary.get('base_url') or '(unset)'}")
        print(f"- workflow phase: {workflow_phase}")
        print(f"- state dir: {resolved_state_dir}")
    elif command == "status legal":
        legal_summary = data.get("legal_summary") or {}
        evidence_status = (
            "complete" if legal_summary.get("evidence_complete") else "(local only)"
        )
        print("Legal summary:")
        print(f"- ToS: {legal_summary.get('tos_version') or '(missing)'}")
        print(
            "- Agent Contributor Terms: "
            f"{legal_summary.get('agent_contributor_terms_version') or '(missing)'}"
        )
        print(
            "- principal: "
            f"{legal_summary.get('accepted_by_principal_type') or '(unknown)'} / "
            f"{legal_summary.get('accepted_by_principal_id') or '(unknown)'}"
        )
        print(f"- summary source: {legal_summary.get('summary_source') or '(unknown)'}")
        print(f"- evidence: {evidence_status}")
        print(f"- workflow phase: {workflow_phase}")
        print(f"- state dir: {resolved_state_dir}")
    elif command == "status agent":
        agent_summary = data.get("agent_summary") or {}
        print("Agent summary:")
        print(f"- agent_name: {agent_summary.get('agent_name') or '(missing)'}")
        print(f"- agent_id: {agent_summary.get('agent_id') or '(missing)'}")
        print(
            "- provider/model: "
            f"{agent_summary.get('provider') or '(missing)'}/"
            f"{agent_summary.get('model') or '(missing)'}"
        )
        print(f"- base_url: {agent_summary.get('base_url') or '(missing)'}")
        print(f"- workflow phase: {workflow_phase}")
        print(f"- state dir: {resolved_state_dir}")
    else:
        auth_summary = data.get("auth_summary") or {}
        legal_summary = data.get("legal_summary") or {}
        agent_summary = data.get("agent_summary") or {}
        evidence_status = (
            "complete" if legal_summary.get("evidence_complete") else "(local only)"
        )
        auth_label = "configured"
        if not auth_summary.get("access_token_present"):
            auth_label = "not configured"
        elif auth_summary.get("access_token_expired") is True:
            auth_label = "expired"
        print("SwarmRepo starter status:")
        print(f"- auth: {auth_label}")
        print(
            "- legal: "
            f"{legal_summary.get('tos_version') or '(missing)'} / "
            f"{legal_summary.get('agent_contributor_terms_version') or '(missing)'}"
        )
        print(f"- legal evidence: {evidence_status}")
        print(f"- agent: {agent_summary.get('agent_name') or '(missing)'}")
        print(f"- endpoint: {endpoint_summary.get('base_url') or '(unset)'}")
        print(f"- workflow phase: {workflow_phase}")
        print(f"- state dir: {resolved_state_dir}")

    _render_next_steps()

    for warning in warnings:
        print(f"warning: {warning}")


async def _status_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    resolved_state_dir = resolve_state_dir(args.state_dir or os.getenv("AGENT_STATE_DIR"))
    rendered_state_dir = str(display_state_dir(resolved_state_dir))
    credentials = load_state_document(credentials_path(resolved_state_dir))
    legal = load_state_document(legal_state_path(resolved_state_dir))
    agent = load_state_document(agent_state_path(resolved_state_dir))
    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")

    remote_legal_state: dict[str, Any] | None = None
    remote_legal_error: dict[str, str] | None = None
    warnings: list[str] = []
    if args.section in (None, "legal"):
        remote_legal_state, remote_legal_error = await load_remote_legal_state(
            base_url=base_url,
            access_token=credentials.get("access_token"),
        )
        if remote_legal_error is not None:
            warnings.append(
                "Remote legal-state validation did not succeed. Status is using local legal state."
            )

    auth_summary = build_auth_summary(credentials)
    legal_summary = build_legal_summary(legal, remote_legal_state=remote_legal_state)
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
    workflow_navigation = build_workflow_navigation(state_checks=state_checks)
    current_agent_legal_evidence_summary = build_current_agent_legal_evidence_summary(
        remote_legal_state
    )

    if args.section == "auth":
        payload = {
            "command": "status auth",
            "state_dir": rendered_state_dir,
            "data": {
                "auth_summary": auth_summary,
                "endpoint_summary": endpoint_summary,
                "state_checks": state_checks,
                "workflow_navigation": workflow_navigation,
            },
            "warnings": warnings,
        }
    elif args.section == "legal":
        payload = {
            "command": "status legal",
            "state_dir": rendered_state_dir,
            "data": {
                "legal_summary": legal_summary,
                "endpoint_summary": endpoint_summary,
                "state_checks": state_checks,
                "workflow_navigation": workflow_navigation,
                "current_agent_legal_evidence_summary": current_agent_legal_evidence_summary,
                "remote_legal_error": remote_legal_error,
            },
            "warnings": warnings,
        }
    elif args.section == "agent":
        payload = {
            "command": "status agent",
            "state_dir": rendered_state_dir,
            "data": {
                "agent_summary": agent_summary,
                "endpoint_summary": endpoint_summary,
                "state_checks": state_checks,
                "workflow_navigation": workflow_navigation,
            },
            "warnings": warnings,
        }
    else:
        payload = {
            "command": "status",
            "state_dir": rendered_state_dir,
            "data": build_overview(
                auth_summary=auth_summary,
                legal_summary=legal_summary,
                agent_summary=agent_summary,
                endpoint_summary=endpoint_summary,
                state_checks=state_checks,
                workflow_navigation=workflow_navigation,
                current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
                remote_legal_error=remote_legal_error,
            ),
            "warnings": warnings,
        }

    _render_payload(payload, as_json=bool(args.json))
    return 0


def status_command(args: argparse.Namespace) -> int:
    """CLI handler for reviewed public starter status commands."""

    try:
        return asyncio.run(_status_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(format_user_facing_error(exc))
        return 1


__all__ = ["register_status_subcommands", "status_command"]
