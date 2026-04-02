"""Audit receipt commands for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any, Mapping

from swarmrepo_sdk import DEFAULT_SWARM_REPO_URL, SwarmClient, SwarmSDKError
from swarmrepo_agent_runtime.env import load_reviewed_dotenv
from swarmrepo_agent_runtime.state import (
    agent_state_path,
    credentials_path,
    display_state_dir,
    load_state_document,
    resolve_state_dir,
)

from .legal_evidence import (
    build_current_agent_legal_evidence_summary,
    build_legal_state_follow_up_lines,
)
from .status_remote import load_remote_legal_state


def register_audit_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register reviewed public audit commands."""

    audit_parser = subparsers.add_parser(
        "audit",
        help="Inspect stable reviewed receipt surfaces.",
    )
    audit_subparsers = audit_parser.add_subparsers(dest="audit_command")

    receipt_parser = audit_subparsers.add_parser(
        "receipt",
        help="Read a stable reviewed task or AMR receipt.",
    )
    lookup_group = receipt_parser.add_mutually_exclusive_group(required=True)
    lookup_group.add_argument(
        "--task-id",
        default=None,
        help="Open issue/task identifier visible to the current authenticated agent.",
    )
    lookup_group.add_argument(
        "--amr-id",
        default=None,
        help="AMR identifier for a stable reviewed receipt lookup.",
    )
    lookup_group.add_argument(
        "--pr-id",
        default=None,
        help="Compatibility alias for an underlying AMR identifier.",
    )
    receipt_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    receipt_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for receipt reads.",
    )
    receipt_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the receipt payload as JSON.",
    )
    receipt_parser.set_defaults(handler=audit_receipt_command)


def _hint(*, kind: str, command: str, reason: str) -> dict[str, str]:
    return {
        "kind": kind,
        "command": command,
        "reason": reason,
    }


def _resolve_state_documents(state_dir: str | None) -> tuple[str, dict[str, Any], dict[str, Any]]:
    resolved_state_dir = str(display_state_dir(resolve_state_dir(state_dir)))
    credentials = load_state_document(credentials_path(resolved_state_dir))
    agent = load_state_document(agent_state_path(resolved_state_dir))
    return resolved_state_dir, credentials, agent


def _apply_local_byok_context(
    client: SwarmClient,
    *,
    agent: Mapping[str, Any],
    credentials: Mapping[str, Any],
) -> None:
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
    client.set_byok_context(
        provider=provider,
        model=model,
        external_api_key=external_api_key,
        base_url_override=base_url_override,
    )


def _task_navigation_hints(task: Mapping[str, Any], *, task_id: str) -> list[dict[str, str]]:
    return [
        _hint(
            kind="canonical_receipt",
            command=f"swarmrepo-agent audit receipt --task-id {task_id}",
            reason="Repeat the same durable task lookup command.",
        ),
        _hint(
            kind="status",
            command="swarmrepo-agent status",
            reason="Inspect the local starter auth, legal, and agent readiness before follow-up.",
        ),
        _hint(
            kind="status_legal",
            command="swarmrepo-agent status legal --json",
            reason="Inspect the authenticated remote legal evidence companion read for the current agent.",
        ),
    ]


def _amr_navigation_hints(*, resolved_amr_id: str) -> list[dict[str, str]]:
    return [
        _hint(
            kind="canonical_receipt",
            command=f"swarmrepo-agent audit receipt --amr-id {resolved_amr_id}",
            reason="Repeat the canonical AMR receipt lookup.",
        ),
        _hint(
            kind="status_agent",
            command="swarmrepo-agent status agent",
            reason="Inspect the current starter agent identity before any follow-up work.",
        ),
        _hint(
            kind="status_legal",
            command="swarmrepo-agent status legal --json",
            reason="Inspect the authenticated remote legal evidence companion read for the current agent.",
        ),
    ]


def _render_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    data = payload.get("data") or {}
    receipt = data.get("receipt") or {}
    receipt_type = data.get("receipt_type") or "(unknown)"
    print("Audit receipt retrieved.")
    print(f"Receipt type: {receipt_type}")
    if receipt_type == "task":
        print(f"Task ID: {receipt.get('id') or '(unknown)'}")
        print(f"Repo ID: {receipt.get('repo_id') or '(unknown)'}")
        print(f"Status: {receipt.get('status') or '(unknown)'}")
        print(f"Reward: {receipt.get('reward_amount') if receipt.get('reward_amount') is not None else '(unknown)'}")
    else:
        print(f"AMR ID: {receipt.get('id') or '(unknown)'}")
        print(f"Repo ID: {receipt.get('repo_id') or '(unknown)'}")
        print(f"Status: {receipt.get('status') or '(unknown)'}")
        if receipt.get("verdict_count") is not None:
            print(f"Verdict count: {receipt.get('verdict_count')}")
        if receipt.get("consensus_status"):
            print(f"Consensus: {receipt.get('consensus_status')}")
    print(f"Canonical receipt: {data.get('canonical_receipt_command') or '(unknown)'}")

    legal_summary = data.get("current_agent_legal_evidence_summary")
    if isinstance(legal_summary, Mapping):
        evidence_status = "complete" if legal_summary.get("evidence_complete") else "partial"
        print(f"Current legal evidence: {evidence_status}")
    else:
        print("Current legal evidence: unavailable")

    for hint in data.get("navigation_hints") or []:
        if isinstance(hint, Mapping) and hint.get("command"):
            print(f"Next: {hint['command']}")

    for line in build_legal_state_follow_up_lines():
        print(line)

    for warning in payload.get("warnings") or []:
        print(f"warning: {warning}")


async def _audit_receipt_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    resolved_state_dir, credentials, agent = _resolve_state_documents(args.state_dir)
    access_token = credentials.get("access_token")
    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")

    remote_legal_state = None
    remote_legal_error = None
    warnings: list[str] = []
    if access_token:
        remote_legal_state, remote_legal_error = await load_remote_legal_state(
            base_url=base_url,
            access_token=str(access_token),
        )
        if remote_legal_error is not None:
            warnings.append(
                "Remote legal-state validation did not succeed. Audit receipt is continuing without a remote legal evidence summary."
            )

    current_agent_legal_evidence_summary = build_current_agent_legal_evidence_summary(
        remote_legal_state
    )

    async with SwarmClient(
        base_url=base_url,
        access_token=str(access_token) if access_token else None,
    ) as client:
        _apply_local_byok_context(client, agent=agent, credentials=credentials)

        if args.task_id:
            if not access_token:
                raise RuntimeError(
                    "audit receipt --task-id requires a local access token in ~/.swarmrepo/credentials.json."
                )
            task = await client.get_open_issue_task(str(args.task_id))
            if task is None:
                raise RuntimeError(
                    "Task receipt could not be found in the authenticated open issue-task view."
                )
            task_id = str(task.id)
            canonical_receipt_command = f"swarmrepo-agent audit receipt --task-id {task_id}"
            payload = {
                "command": "audit receipt",
                "state_dir": resolved_state_dir,
                "data": {
                    "receipt_type": "task",
                    "receipt": task.model_dump(mode="json"),
                    "canonical_receipt_command": canonical_receipt_command,
                    "receipt_lookup": {
                        "requested_kind": "task_id",
                        "requested_id": str(args.task_id),
                        "resolved_kind": "issue_id",
                        "resolved_id": task_id,
                        "lookup_mode": "task_id_alias_to_open_issue",
                    },
                    "navigation_hints": _task_navigation_hints(task.model_dump(mode="json"), task_id=task_id),
                    "current_agent_legal_evidence_summary": current_agent_legal_evidence_summary,
                    "current_agent_legal_error": remote_legal_error,
                },
                "warnings": [
                    "audit receipt --task-id currently resolves through the authenticated open issue-task view."
                ]
                + warnings,
            }
            _render_payload(payload, as_json=bool(args.json))
            return 0

        requested_id = str(args.amr_id or args.pr_id)
        lookup_mode = "amr_id"
        if args.pr_id:
            lookup_mode = "pr_id_alias_to_amr"
            warnings.append(
                "audit receipt --pr-id currently resolves through the underlying AMR identifier."
            )
        receipt = await client.get_amr_receipt(requested_id, include_bearer=None)
        resolved_amr_id = str(receipt.id)
        payload = {
            "command": "audit receipt",
            "state_dir": resolved_state_dir,
            "data": {
                "receipt_type": "amr",
                "receipt": receipt.model_dump(mode="json"),
                "canonical_receipt_command": f"swarmrepo-agent audit receipt --amr-id {resolved_amr_id}",
                "receipt_lookup": {
                    "requested_kind": "pr_id" if args.pr_id else "amr_id",
                    "requested_id": requested_id,
                    "resolved_kind": "amr_id",
                    "resolved_id": resolved_amr_id,
                    "lookup_mode": lookup_mode,
                },
                "navigation_hints": _amr_navigation_hints(resolved_amr_id=resolved_amr_id),
                "current_agent_legal_evidence_summary": current_agent_legal_evidence_summary,
                "current_agent_legal_error": remote_legal_error,
            },
            "warnings": warnings,
        }
        _render_payload(payload, as_json=bool(args.json))
        return 0


def audit_receipt_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent audit receipt`."""

    try:
        return asyncio.run(_audit_receipt_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(str(exc))
        return 1


__all__ = ["audit_receipt_command", "register_audit_subcommands"]
