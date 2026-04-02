"""Agent commands for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import os
from textwrap import dedent

from swarmrepo_sdk import DEFAULT_SWARM_REPO_URL, SwarmClient, SwarmSDKError
from swarmrepo_agent_runtime.env import load_reviewed_dotenv
from swarmrepo_agent_runtime.state import (
    agent_state_path,
    credentials_path,
    display_state_dir,
    legal_state_path,
    load_state_document,
    resolve_state_dir,
)

from .identity_bootstrap import ensure_identity
from .onboard_result import build_onboarding_payload, render_onboarding_payload
from .status_remote import load_remote_legal_state


def register_agent_subcommands(
    subparsers: argparse._SubParsersAction,
    *,
    help_handler,
) -> None:
    """Register reviewed public agent commands."""

    agent_parser = subparsers.add_parser(
        "agent",
        help="Onboard and inspect the reviewed public starter identity lifecycle.",
        description=dedent(
            """\
            Reviewed public agent commands.

            `agent onboard` is the stable idempotent entrypoint that brings the
            current machine into a ready state for reviewed AI workflows. It
            reuses `~/.swarmrepo` local state when possible and falls back to
            the reviewed first-run registration flow when needed.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent agent onboard
              swarmrepo-agent agent onboard --yes --json
              swarmrepo-agent agent onboard --state-dir ~/.swarmrepo --base-url https://api.swarmrepo.com
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    agent_parser.set_defaults(handler=lambda _args, parser=agent_parser: help_handler(parser))
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

    onboard_parser = agent_subparsers.add_parser(
        "onboard",
        help="Bring the current machine to a ready reviewed starter state.",
        description=dedent(
            """\
            Idempotently onboard the reviewed public starter.

            The command:
            - reuses a valid local starter access token when one exists
            - runs reviewed first-run registration when local auth is missing
            - records state in `~/.swarmrepo`
            - returns follow-up commands for the next public workflow steps

            Use `--yes` to allow non-interactive legal acceptance after the
            human operator has already reviewed the active legal summaries.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent agent onboard
              swarmrepo-agent agent onboard --yes
              swarmrepo-agent agent onboard --yes --json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    onboard_parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-accept the active legal summaries after prior human review.",
    )
    onboard_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    onboard_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for onboarding validation.",
    )
    onboard_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the onboarding payload as JSON.",
    )
    onboard_parser.set_defaults(handler=agent_onboard_command)


def _read_local_state(state_dir: str) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        load_state_document(credentials_path(state_dir)),
        load_state_document(legal_state_path(state_dir)),
        load_state_document(agent_state_path(state_dir)),
    )


def _resolve_onboarding_state(
    *,
    access_token_before: str | None,
    access_token_after: str | None,
) -> tuple[str, list[str]]:
    if access_token_before and access_token_before == access_token_after:
        return "already_ready", ["auth_validate"]
    return "registered_ready", [
        "legal_requirements",
        "legal_accept",
        "agent_register",
        "auth_validate",
    ]


async def _agent_onboard_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    requested_state_dir = resolve_state_dir(args.state_dir or os.getenv("AGENT_STATE_DIR"))
    credentials_before, _, _ = _read_local_state(str(requested_state_dir))
    access_token_before = str(credentials_before.get("access_token") or "").strip() or None
    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")

    async with SwarmClient(base_url=base_url) as client:
        _, resolved_state_dir = await ensure_identity(
            client,
            state_dir=requested_state_dir,
            auto_accept="yes" if args.yes else None,
        )

    rendered_state_dir = str(display_state_dir(resolved_state_dir))
    credentials, legal, agent = _read_local_state(rendered_state_dir)
    access_token_after = str(credentials.get("access_token") or "").strip() or None
    onboarding_state, steps_executed = _resolve_onboarding_state(
        access_token_before=access_token_before,
        access_token_after=access_token_after,
    )

    remote_legal_state = None
    remote_legal_error = None
    warnings: list[str] = []
    if access_token_after:
        remote_legal_state, remote_legal_error = await load_remote_legal_state(
            base_url=base_url,
            access_token=access_token_after,
        )
        if remote_legal_error is not None:
            warnings.append(
                "Remote legal-state validation did not succeed. agent onboard is using local legal state."
            )

    payload = build_onboarding_payload(
        onboarding_state=onboarding_state,
        state_dir=rendered_state_dir,
        base_url=base_url,
        credentials=credentials,
        legal=legal,
        agent=agent,
        steps_executed=steps_executed,
        remote_legal_state=remote_legal_state,
        remote_legal_error=remote_legal_error,
        warnings=warnings,
    )
    render_onboarding_payload(payload, as_json=bool(args.json))
    return 0


def agent_onboard_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent agent onboard`."""

    try:
        return asyncio.run(_agent_onboard_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(str(exc))
        return 1


__all__ = ["agent_onboard_command", "register_agent_subcommands"]
