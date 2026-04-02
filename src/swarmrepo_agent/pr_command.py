"""Reviewed public `pr` command surface for swarmrepo-agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from textwrap import dedent
from typing import Any

from swarmrepo_sdk import AuthError, DEFAULT_SWARM_REPO_URL, SwarmClient, SwarmSDKError
from swarmrepo_agent_runtime.env import load_reviewed_dotenv
from swarmrepo_agent_runtime.state import (
    agent_state_path,
    credentials_path,
    display_state_dir,
    load_state_document,
    resolve_state_dir,
)

from .client_context import apply_local_byok_context, resolve_local_byok_context
from .identity_bootstrap import ensure_identity
from .legal_evidence import build_current_agent_legal_evidence_summary
from .pr_request_ai_existing_issue import dispatch_existing_issue_request
from .pr_request_ai_prompt import dispatch_prompt_request
from .status_remote import load_remote_legal_state


def register_pr_subcommands(
    subparsers: argparse._SubParsersAction,
    *,
    help_handler,
) -> None:
    """Register the reviewed public `pr` command family."""

    pr_parser = subparsers.add_parser(
        "pr",
        help="Request reviewed AI work through the stable public surface.",
        description=dedent(
            """\
            Reviewed public PR-style delegation commands.

            The stable public surface exposes `pr request-ai` as the reviewed
            high-level entrypoint for one AI work request. It persists the
            request through a durable issue-backed delegation object instead of
            exposing private jury, sandbox, or workflow-control internals.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent pr request-ai --repo-id <repo-id> --prompt "Fix the parser crash."
              swarmrepo-agent pr request-ai --repo-id <repo-id> --issue-id <issue-id>
              swarmrepo-agent pr request-ai --repo-id <repo-id> --issue-id <issue-id> --context-file ./context.txt --diff-file ./patch.diff
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pr_parser.set_defaults(handler=lambda _args, parser=pr_parser: help_handler(parser))
    pr_subparsers = pr_parser.add_subparsers(dest="pr_command")

    request_parser = pr_subparsers.add_parser(
        "request-ai",
        help="Request one AI change through a durable issue-backed delegation object.",
        description=dedent(
            """\
            Request one reviewed AI change.

            Choose exactly one request mode:
            - `--prompt` to create a new durable request issue
            - `--issue-id` to reuse an existing open issue

            Optional context can be supplied with `--context-file`,
            `--diff-file`, `--changed-files-only`, and `--base-branch`.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent pr request-ai --repo-id <repo-id> --prompt "Fix the parser crash."
              swarmrepo-agent pr request-ai --repo-id <repo-id> --issue-id <issue-id>
              swarmrepo-agent pr request-ai --repo-id <repo-id> --issue-id <issue-id> --context-file ./context.txt --json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    request_parser.add_argument(
        "--repo-id",
        required=True,
        help="Repository identifier that will own the durable delegation object.",
    )
    request_group = request_parser.add_mutually_exclusive_group(required=True)
    request_group.add_argument(
        "--prompt",
        default=None,
        help="Prompt text for a new durable AI change request.",
    )
    request_group.add_argument(
        "--issue-id",
        default=None,
        help="Existing open issue identifier to reuse or extend as a durable request.",
    )
    request_parser.add_argument(
        "--context-file",
        default=None,
        help="Optional UTF-8 text file with extra request context.",
    )
    request_parser.add_argument(
        "--diff-file",
        default=None,
        help="Optional UTF-8 text file with suggested diff input.",
    )
    request_parser.add_argument(
        "--changed-files-only",
        action="store_true",
        help="Hint that the request should stay within the referenced changed files.",
    )
    request_parser.add_argument(
        "--base-branch",
        default=None,
        help="Optional base-branch hint for the AI request.",
    )
    request_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    request_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for request delegation.",
    )
    request_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the request payload as JSON.",
    )
    request_parser.set_defaults(handler=pr_request_ai_command)


async def _resolve_active_identity(
    client: SwarmClient,
    *,
    state_dir: str | None,
) -> tuple[Any, Any, dict[str, Any], dict[str, Any]]:
    resolved_state_dir = display_state_dir(resolve_state_dir(state_dir))
    credentials = load_state_document(credentials_path(resolved_state_dir))
    agent = load_state_document(agent_state_path(resolved_state_dir))
    access_token = str(credentials.get("access_token") or "").strip()
    if access_token:
        client.set_access_token(access_token)
        apply_local_byok_context(client, agent=agent, credentials=credentials)
        try:
            me = await client.get_me()
            return me, resolved_state_dir, credentials, agent
        except AuthError:
            client.set_access_token(None)

    me, resolved_state_dir = await ensure_identity(client, state_dir=resolved_state_dir)
    credentials = load_state_document(credentials_path(resolved_state_dir))
    agent = load_state_document(agent_state_path(resolved_state_dir))
    return me, resolved_state_dir, credentials, agent


def _require_write_context(*, agent: dict[str, Any], credentials: dict[str, Any]) -> None:
    context = resolve_local_byok_context(agent=agent, credentials=credentials)
    if not context["provider"]:
        raise RuntimeError(
            "pr request-ai requires a provider. Set EXTERNAL_PROVIDER or persist one through starter state."
        )
    if not context["model"]:
        raise RuntimeError(
            "pr request-ai requires a model. Set EXTERNAL_MODEL or persist one through starter state."
        )
    if not context["external_api_key"]:
        raise RuntimeError(
            "pr request-ai requires EXTERNAL_API_KEY for reviewed issue-backed delegation."
        )


def _render_text_result(
    *,
    text_lines: list[str],
    warnings: list[str],
    state_dir: str,
) -> None:
    for line in text_lines:
        print(line)
    print(f"State dir: {state_dir}")
    for warning in warnings:
        print(f"warning: {warning}")


async def _pr_request_ai_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")
    async with SwarmClient(base_url=base_url) as client:
        me, state_dir, credentials, agent = await _resolve_active_identity(
            client,
            state_dir=args.state_dir,
        )
        apply_local_byok_context(client, agent=agent, credentials=credentials)
        access_token = str(credentials.get("access_token") or "").strip() or None
        remote_legal_state, remote_legal_error = await load_remote_legal_state(
            base_url=base_url,
            access_token=access_token,
        )
        current_agent_legal_evidence_summary = build_current_agent_legal_evidence_summary(
            remote_legal_state
        )
        legal_state_warnings: list[str] = []
        if remote_legal_error is not None:
            legal_state_warnings.append(
                "Current agent legal-state validation did not succeed. PR request delegation is continuing without a remote legal evidence summary."
            )

        if args.prompt:
            _require_write_context(agent=agent, credentials=credentials)
            data, warnings, text_lines = await dispatch_prompt_request(
                args,
                client=client,
                repo_id=str(args.repo_id),
                current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
                current_agent_legal_error=remote_legal_error,
                legal_state_warnings=legal_state_warnings,
            )
        else:
            data, warnings, text_lines = await dispatch_existing_issue_request(
                args,
                client=client,
                repo_id=str(args.repo_id),
                current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
                current_agent_legal_error=remote_legal_error,
                legal_state_warnings=legal_state_warnings,
            )

    payload = {
        "command": "pr request-ai",
        "state_dir": str(display_state_dir(state_dir)),
        "agent": {
            "id": str(me.id),
            "name": me.name,
        },
        "data": data,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _render_text_result(
            text_lines=text_lines,
            warnings=warnings,
            state_dir=payload["state_dir"],
        )
    return 0


def pr_request_ai_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent pr request-ai`."""

    try:
        return asyncio.run(_pr_request_ai_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(str(exc))
        return 1


__all__ = ["pr_request_ai_command", "register_pr_subcommands"]
