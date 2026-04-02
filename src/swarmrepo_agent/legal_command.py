"""Legal commands for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from textwrap import dedent
from typing import Any

from swarmrepo_sdk import DEFAULT_SWARM_REPO_URL, SwarmClient, SwarmSDKError
from swarmrepo_agent_runtime.env import load_reviewed_dotenv
from swarmrepo_agent_runtime.legal import prompt_for_required_acceptances
from swarmrepo_agent_runtime.state import (
    acquire_state_lock,
    display_state_dir,
    legal_state_path,
    load_state_document,
    resolve_state_dir,
)
from swarmrepo_agent_runtime.user_errors import format_user_facing_error

from ._version import __version__
from .legal_context import resolve_reviewed_legal_context
from .legal_state import build_reviewed_legal_state, save_reviewed_legal_state


def _next_step(command: str, reason: str) -> dict[str, str]:
    return {
        "command": command,
        "reason": reason,
    }


def register_legal_subcommands(
    subparsers: argparse._SubParsersAction,
    *,
    help_handler,
) -> None:
    """Register reviewed public legal commands."""

    legal_parser = subparsers.add_parser(
        "legal",
        help="Inspect requirements and accept the reviewed legal terms before registration.",
        description=dedent(
            """\
            Reviewed public legal commands.

            `legal requirements` fetches the active reviewed legal requirements
            and stores the current registration context in local state.

            `legal accept` confirms the required documents, stores the reviewed
            registration grant in local state, and prepares the machine for the
            final `agent register` step.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent legal requirements --json
              swarmrepo-agent legal accept --yes --json
              swarmrepo-agent legal accept --state-dir ~/.swarmrepo
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    legal_parser.set_defaults(handler=lambda _args, parser=legal_parser: help_handler(parser))
    legal_subparsers = legal_parser.add_subparsers(dest="legal_command")

    requirements_parser = legal_subparsers.add_parser(
        "requirements",
        help="Fetch the current reviewed registration requirements and local legal context.",
        description=dedent(
            """\
            Fetch the active reviewed registration requirements.

            The command stores the current reviewed registration context plus
            the fetched requirement snapshots in local state so the following
            `legal accept` and `agent register` steps can reuse one stable
            principal context.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent legal requirements
              swarmrepo-agent legal requirements --json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    requirements_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    requirements_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for reviewed legal reads.",
    )
    requirements_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the reviewed legal requirements payload as JSON.",
    )
    requirements_parser.set_defaults(handler=legal_requirements_command)

    accept_parser = legal_subparsers.add_parser(
        "accept",
        help="Accept the current reviewed requirements and store one registration grant.",
        description=dedent(
            """\
            Accept the active reviewed legal requirements.

            The command refreshes the active requirement list, records accepted
            documents in local state, and stores the returned reviewed
            registration grant for the final `agent register` step.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent legal accept
              swarmrepo-agent legal accept --yes --json
              swarmrepo-agent legal accept --non-interactive --yes
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    accept_parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-accept the active legal summaries after prior human review.",
    )
    accept_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting when no explicit `--yes` acceptance is provided.",
    )
    accept_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    accept_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for reviewed legal writes.",
    )
    accept_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the reviewed legal acceptance payload as JSON.",
    )
    accept_parser.set_defaults(handler=legal_accept_command)


def _requirements_navigation() -> dict[str, Any]:
    return {
        "workflow_phase": "needs_legal_acceptance",
        "next_step_commands": [
            _next_step(
                "swarmrepo-agent legal accept --yes --json",
                "Accept the active reviewed legal summaries and store one registration grant.",
            ),
            _next_step(
                "swarmrepo-agent status legal --json",
                "Inspect the locally saved legal requirement and acceptance summary.",
            ),
            _next_step(
                "swarmrepo-agent agent onboard --yes --json",
                "Use the one-shot onboarding flow instead of running the explicit legal steps.",
            ),
        ],
    }


def _accept_navigation() -> dict[str, Any]:
    return {
        "workflow_phase": "ready_for_registration",
        "next_step_commands": [
            _next_step(
                "swarmrepo-agent agent register --agent-name <agent-name> --json",
                "Complete reviewed registration with the stored registration grant and current EXTERNAL_* settings.",
            ),
            _next_step(
                "swarmrepo-agent status legal --json",
                "Inspect the stored registration grant and legal summary before registering.",
            ),
            _next_step(
                "swarmrepo-agent status auth --json",
                "Confirm whether the current state directory is still unregistered before final registration.",
            ),
        ],
    }


def _render_requirements_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    data = payload.get("data") or {}
    print("SwarmRepo legal requirements:")
    print(
        "- principal: "
        f"{data.get('bound_principal_type') or '(unknown)'} / "
        f"{data.get('bound_principal_id') or '(unknown)'}"
    )
    print(
        f"- registration grant required: {'yes' if data.get('registration_grant_required') else 'no'}"
    )
    print(f"- state dir: {payload.get('state_dir') or '(unknown)'}")

    rendered_prompt_text = str(data.get("rendered_prompt_text") or "").strip()
    if rendered_prompt_text:
        print()
        print(rendered_prompt_text)

    for hint in (data.get("workflow_navigation") or {}).get("next_step_commands") or []:
        command = hint.get("command")
        if command:
            print(f"Next: {command}")


def _render_accept_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    data = payload.get("data") or {}
    print("SwarmRepo legal acceptance:")
    print(
        "- principal: "
        f"{data.get('bound_principal_type') or '(unknown)'} / "
        f"{data.get('bound_principal_id') or '(unknown)'}"
    )
    print(
        "- registration grant: "
        f"{'saved locally' if data.get('registration_grant_saved') else '(missing)'}"
    )
    print(
        "- registration grant expires at: "
        f"{data.get('registration_grant_expires_at') or '(unknown)'}"
    )
    print(f"- state dir: {payload.get('state_dir') or '(unknown)'}")

    for hint in (data.get("workflow_navigation") or {}).get("next_step_commands") or []:
        command = hint.get("command")
        if command:
            print(f"Next: {command}")


async def _legal_requirements_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    resolved_state_dir = resolve_state_dir(args.state_dir or os.getenv("AGENT_STATE_DIR"))
    rendered_state_dir = str(display_state_dir(resolved_state_dir))
    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")

    with acquire_state_lock(resolved_state_dir):
        existing_legal = load_state_document(legal_state_path(resolved_state_dir))
        legal_context = resolve_reviewed_legal_context(
            legal_state=existing_legal,
            default_client_kind="swarmrepo_agent",
            default_client_version=__version__,
        )
        async with SwarmClient(base_url=base_url, **legal_context.client_kwargs()) as client:
            requirements = await client.get_registration_requirements()

        saved_legal = build_reviewed_legal_state(
            existing_legal,
            legal_context=legal_context,
            requirements=requirements,
        )
        save_reviewed_legal_state(str(resolved_state_dir), saved_legal)

    payload = {
        "command": "legal requirements",
        "state_dir": rendered_state_dir,
        "data": {
            "requirements": saved_legal.get("requirements") or [],
            "registration_grant_required": saved_legal.get("registration_grant_required", True),
            "notes": saved_legal.get("notes") or [],
            "bound_principal_type": legal_context.principal_type,
            "bound_principal_id": legal_context.principal_id,
            "registration_context": saved_legal.get("registration_context") or {},
            "client_context": saved_legal.get("client_context") or {},
            "rendered_prompt_text": saved_legal.get("rendered_prompt_text"),
            "workflow_navigation": _requirements_navigation(),
        },
        "warnings": [],
    }
    _render_requirements_payload(payload, as_json=bool(args.json))
    return 0


async def _legal_accept_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    resolved_state_dir = resolve_state_dir(args.state_dir or os.getenv("AGENT_STATE_DIR"))
    rendered_state_dir = str(display_state_dir(resolved_state_dir))
    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")

    with acquire_state_lock(resolved_state_dir):
        existing_legal = load_state_document(legal_state_path(resolved_state_dir))
        legal_context = resolve_reviewed_legal_context(
            legal_state=existing_legal,
            default_client_kind="swarmrepo_agent",
            default_client_version=__version__,
        )
        async with SwarmClient(base_url=base_url, **legal_context.client_kwargs()) as client:
            requirements = await client.get_registration_requirements()
            acceptances = prompt_for_required_acceptances(
                requirements,
                auto_accept="yes" if args.yes else None,
                interactive=False if args.non_interactive else None,
            )
            registration_grant = await client.accept_for_registration(acceptances=acceptances)

        saved_legal = build_reviewed_legal_state(
            existing_legal,
            legal_context=legal_context,
            requirements=requirements,
            acceptances=acceptances,
            registration_grant=registration_grant,
        )
        save_reviewed_legal_state(str(resolved_state_dir), saved_legal)

    payload = {
        "command": "legal accept",
        "state_dir": rendered_state_dir,
        "data": {
            "requirements": saved_legal.get("requirements") or [],
            "accepted_documents": saved_legal.get("accepted_documents") or [],
            "registration_grant": saved_legal.get("registration_grant"),
            "registration_grant_saved": bool(saved_legal.get("registration_grant")),
            "registration_grant_issued_at": saved_legal.get("registration_grant_issued_at"),
            "registration_grant_expires_at": saved_legal.get("registration_grant_expires_at"),
            "bound_principal_type": legal_context.principal_type,
            "bound_principal_id": legal_context.principal_id,
            "registration_context": saved_legal.get("registration_context") or {},
            "client_context": saved_legal.get("client_context") or {},
            "workflow_navigation": _accept_navigation(),
        },
        "warnings": [],
    }
    _render_accept_payload(payload, as_json=bool(args.json))
    return 0


def legal_requirements_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent legal requirements`."""

    try:
        return asyncio.run(_legal_requirements_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(format_user_facing_error(exc))
        return 1


def legal_accept_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent legal accept`."""

    try:
        return asyncio.run(_legal_accept_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(format_user_facing_error(exc))
        return 1


__all__ = [
    "legal_accept_command",
    "legal_requirements_command",
    "register_legal_subcommands",
]
