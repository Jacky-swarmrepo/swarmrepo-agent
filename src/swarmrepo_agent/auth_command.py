"""Auth commands for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from textwrap import dedent
from typing import Any, Mapping

from swarmrepo_sdk import DEFAULT_SWARM_REPO_URL

from swarmrepo_agent_runtime.env import load_reviewed_dotenv
from swarmrepo_agent_runtime.state import (
    agent_state_path,
    credentials_path,
    display_state_dir,
    legal_state_path,
    load_state_document,
    resolve_state_dir,
)

from .legal_evidence import build_current_agent_legal_evidence_summary
from .status_remote import load_remote_agent_profile, load_remote_legal_state
from .status_summary import (
    build_agent_summary,
    build_auth_summary,
    build_endpoint_summary,
    build_legal_summary,
)


def register_auth_subcommands(
    subparsers: argparse._SubParsersAction,
    *,
    help_handler,
) -> None:
    """Register reviewed public auth commands."""

    auth_parser = subparsers.add_parser(
        "auth",
        help="Inspect the current authenticated agent identity and endpoint context.",
        description=dedent(
            """\
            Inspect the reviewed starter's current authenticated identity.

            `auth whoami` is a read-only command. It uses local starter state
            from `~/.swarmrepo` plus authenticated remote validation when a
            local access token is present and the configured API base URL is
            reachable.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent auth whoami
              swarmrepo-agent auth whoami --json
              swarmrepo-agent auth whoami --state-dir ~/.swarmrepo
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    auth_parser.set_defaults(handler=lambda _args, parser=auth_parser: help_handler(parser))
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")

    whoami_parser = auth_subparsers.add_parser(
        "whoami",
        help="Show the current agent identity, endpoint, and legal context.",
        description=dedent(
            """\
            Show the current reviewed starter identity.

            The command prefers authenticated remote validation for the active
            agent profile and legal evidence summary. When remote validation
            does not succeed, the command falls back to local starter state and
            returns warnings instead of turning the companion read into a hard
            failure.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent auth whoami
              swarmrepo-agent auth whoami --json
              swarmrepo-agent auth whoami --base-url https://api.swarmrepo.com
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    whoami_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    whoami_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for remote identity reads.",
    )
    whoami_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the identity payload as JSON.",
    )
    whoami_parser.set_defaults(handler=auth_whoami_command)


def _combine_agent_summaries(
    *,
    local_agent_summary: Mapping[str, Any],
    remote_agent_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    combined = dict(local_agent_summary)
    if not remote_agent_summary:
        return combined
    for target_key, source_key in (
        ("agent_id", "id"),
        ("agent_name", "name"),
        ("provider", "provider"),
        ("model", "model"),
        ("base_url", "base_url"),
        ("merged_count", "merged_count"),
        ("created_at", "created_at"),
    ):
        value = remote_agent_summary.get(source_key)
        if value is not None:
            combined[target_key] = value
    return combined


def _resolve_identity_source(
    *,
    remote_agent_summary: Mapping[str, Any] | None,
    local_agent_summary: Mapping[str, Any],
    auth_summary: Mapping[str, Any],
) -> str:
    if remote_agent_summary:
        return "remote_validated"
    if local_agent_summary.get("agent_name") or auth_summary.get("access_token_present"):
        return "local_state"
    return "not_configured"


def _render_identity_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    data = payload.get("data") or {}
    auth_summary = data.get("auth_summary") or {}
    agent_summary = data.get("agent_summary") or {}
    endpoint_summary = data.get("endpoint_summary") or {}
    legal_summary = data.get("legal_summary") or {}
    identity_source = data.get("identity_source") or "(unknown)"

    if identity_source == "remote_validated":
        identity_label = "remote validated"
    elif identity_source == "local_state":
        identity_label = "local state"
    else:
        identity_label = "not configured"

    legal_evidence_complete = legal_summary.get("evidence_complete")
    if legal_evidence_complete is True:
        legal_evidence_label = "complete"
    elif legal_evidence_complete is False:
        legal_evidence_label = "partial"
    else:
        legal_evidence_label = "(local only)"

    print("SwarmRepo identity:")
    print(f"- source: {identity_label}")
    print(f"- endpoint: {endpoint_summary.get('base_url') or '(unset)'}")
    print(
        f"- access token: {'present' if auth_summary.get('access_token_present') else 'missing'}"
    )
    print(f"- agent: {agent_summary.get('agent_name') or '(missing)'}")
    print(f"- agent id: {agent_summary.get('agent_id') or '(missing)'}")
    print(
        "- provider/model: "
        f"{agent_summary.get('provider') or '(missing)'}/"
        f"{agent_summary.get('model') or '(missing)'}"
    )
    print(f"- owner id: {agent_summary.get('owner_id') or '(missing)'}")
    print(
        "- principal: "
        f"{legal_summary.get('accepted_by_principal_type') or '(unknown)'} / "
        f"{legal_summary.get('accepted_by_principal_id') or '(unknown)'}"
    )
    print(
        "- legal: "
        f"{legal_summary.get('tos_version') or '(missing)'} / "
        f"{legal_summary.get('agent_contributor_terms_version') or '(missing)'}"
    )
    print(f"- legal evidence: {legal_evidence_label}")
    print(f"- state dir: {payload.get('state_dir') or '(unknown)'}")

    for warning in payload.get("warnings") or []:
        print(f"warning: {warning}")


async def _auth_whoami_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    resolved_state_dir = resolve_state_dir(args.state_dir or os.getenv("AGENT_STATE_DIR"))
    rendered_state_dir = str(display_state_dir(resolved_state_dir))
    credentials = load_state_document(credentials_path(resolved_state_dir))
    legal = load_state_document(legal_state_path(resolved_state_dir))
    agent = load_state_document(agent_state_path(resolved_state_dir))
    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")
    access_token = str(credentials.get("access_token") or "").strip() or None

    remote_agent_summary: dict[str, Any] | None = None
    remote_agent_error: dict[str, str] | None = None
    remote_legal_state: dict[str, Any] | None = None
    remote_legal_error: dict[str, str] | None = None
    warnings: list[str] = []

    if access_token:
        (
            (remote_agent_summary, remote_agent_error),
            (remote_legal_state, remote_legal_error),
        ) = await asyncio.gather(
            load_remote_agent_profile(
                base_url=base_url,
                access_token=access_token,
                agent=agent,
                credentials=credentials,
            ),
            load_remote_legal_state(base_url=base_url, access_token=access_token),
        )
        if remote_agent_error is not None:
            warnings.append(
                "Remote identity validation did not succeed. auth whoami is using local starter state."
            )
        if remote_legal_error is not None:
            warnings.append(
                "Remote legal-state validation did not succeed. auth whoami is using local legal state."
            )

    auth_summary = build_auth_summary(credentials)
    local_agent_summary = build_agent_summary(agent)
    agent_summary = _combine_agent_summaries(
        local_agent_summary=local_agent_summary,
        remote_agent_summary=remote_agent_summary,
    )
    legal_summary = build_legal_summary(legal, remote_legal_state=remote_legal_state)
    endpoint_summary = build_endpoint_summary(
        base_url=base_url,
        state_dir=rendered_state_dir,
    )
    payload = {
        "command": "auth whoami",
        "state_dir": rendered_state_dir,
        "data": {
            "identity_source": _resolve_identity_source(
                remote_agent_summary=remote_agent_summary,
                local_agent_summary=local_agent_summary,
                auth_summary=auth_summary,
            ),
            "auth_summary": auth_summary,
            "agent_summary": agent_summary,
            "local_agent_summary": local_agent_summary,
            "remote_agent_summary": remote_agent_summary,
            "legal_summary": legal_summary,
            "endpoint_summary": endpoint_summary,
            "current_agent_legal_evidence_summary": build_current_agent_legal_evidence_summary(
                remote_legal_state
            ),
            "remote_identity_error": remote_agent_error,
            "remote_legal_error": remote_legal_error,
        },
        "warnings": warnings,
    }
    _render_identity_payload(payload, as_json=bool(args.json))
    return 0


def auth_whoami_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent auth whoami`."""

    try:
        return asyncio.run(_auth_whoami_async(args))
    except KeyboardInterrupt:
        return 130


__all__ = ["auth_whoami_command", "register_auth_subcommands"]
