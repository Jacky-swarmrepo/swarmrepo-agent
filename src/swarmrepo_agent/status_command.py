"""Status commands for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from swarmrepo_sdk import DEFAULT_SWARM_REPO_URL

from swarmrepo_agent_runtime.state import (
    agent_state_path,
    credentials_path,
    legal_state_path,
    load_state_document,
    resolve_state_dir,
)

from .status_remote import load_remote_legal_state
from .status_summary import (
    build_agent_summary,
    build_auth_summary,
    build_endpoint_summary,
    build_legal_summary,
    build_overview,
)


def register_status_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register the reviewed starter status commands."""

    status_parser = subparsers.add_parser(
        "status",
        help="Inspect local starter state and remote legal evidence summaries.",
        description=(
            "Inspect local starter state. `status legal` prefers the authenticated "
            "remote legal-state summary when a local access token and reachable "
            "API base URL are available."
        ),
    )
    status_parser.add_argument(
        "section",
        nargs="?",
        choices=["legal", "auth", "agent"],
        help="Optional status section.",
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

    if command == "status auth":
        auth_summary = data.get("auth_summary") or {}
        print("Authentication summary:")
        print(
            f"- access token: {'present' if auth_summary.get('access_token_present') else 'missing'}"
        )
        print(
            f"- refresh token: {'present' if auth_summary.get('refresh_token_present') else 'missing'}"
        )
        print(
            f"- refresh token storage: {auth_summary.get('refresh_token_storage') or '(unknown)'}"
        )
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
        print(f"- evidence: {evidence_status}")
        print("See also: swarmrepo-agent status legal --json")
    elif command == "status agent":
        agent_summary = data.get("agent_summary") or {}
        print("Agent summary:")
        print(f"- agent_name: {agent_summary.get('agent_name') or '(missing)'}")
        print(
            "- provider/model: "
            f"{agent_summary.get('provider') or '(missing)'}/"
            f"{agent_summary.get('model') or '(missing)'}"
        )
        print(f"- base_url: {agent_summary.get('base_url') or '(missing)'}")
    else:
        auth_summary = data.get("auth_summary") or {}
        legal_summary = data.get("legal_summary") or {}
        agent_summary = data.get("agent_summary") or {}
        endpoint_summary = data.get("endpoint_summary") or {}
        evidence_status = (
            "complete" if legal_summary.get("evidence_complete") else "(local only)"
        )
        print("SwarmRepo starter status:")
        print(
            f"- auth: {'configured' if auth_summary.get('access_token_present') else 'not configured'}"
        )
        print(
            "- legal: "
            f"{legal_summary.get('tos_version') or '(missing)'} / "
            f"{legal_summary.get('agent_contributor_terms_version') or '(missing)'}"
        )
        print(f"- legal evidence: {evidence_status}")
        print(f"- agent: {agent_summary.get('agent_name') or '(missing)'}")
        print(f"- endpoint: {endpoint_summary.get('base_url') or '(unset)'}")

    for warning in warnings:
        print(f"warning: {warning}")


async def _status_async(args: argparse.Namespace) -> int:
    load_dotenv()

    resolved_state_dir = resolve_state_dir(args.state_dir or os.getenv("AGENT_STATE_DIR"))
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
        state_dir=str(Path(resolved_state_dir)),
    )

    if args.section == "auth":
        payload = {
            "command": "status auth",
            "data": {"auth_summary": auth_summary},
            "warnings": warnings,
        }
    elif args.section == "legal":
        payload = {
            "command": "status legal",
            "data": {
                "legal_summary": legal_summary,
                "remote_legal_error": remote_legal_error,
            },
            "warnings": warnings,
        }
    elif args.section == "agent":
        payload = {
            "command": "status agent",
            "data": {"agent_summary": agent_summary},
            "warnings": warnings,
        }
    else:
        payload = {
            "command": "status",
            "data": build_overview(
                auth_summary=auth_summary,
                legal_summary=legal_summary,
                agent_summary=agent_summary,
                endpoint_summary=endpoint_summary,
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


__all__ = ["register_status_subcommands", "status_command"]
