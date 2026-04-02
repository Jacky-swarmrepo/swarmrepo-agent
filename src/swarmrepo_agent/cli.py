"""Stable reviewed starter entrypoints for swarmrepo-agent."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from textwrap import dedent

from ._version import __version__
from .agent_command import register_agent_subcommands
from .audit_command import register_audit_subcommands
from .auth_command import register_auth_subcommands
from .pr_command import register_pr_subcommands
from .repo_command import register_repo_subcommands
from .status_command import register_status_subcommands
from swarmrepo_agent_runtime.user_errors import format_user_facing_error
from swarmrepo_sdk import SwarmSDKError


def _print_help_and_return(parser: argparse.ArgumentParser) -> int:
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swarmrepo-agent",
        description=dedent(
            """\
            Reviewed public starter CLI for SwarmRepo-compatible agents.

            The stable public surface focuses on:
            - first-run onboarding and local state reuse
            - idempotent machine onboarding to a ready reviewed state
            - authenticated identity and legal-state inspection
            - reviewed repository creation
            - reviewed source-material import into new independent repositories
            - local repo binding for reviewed Git Smart HTTP workflows
            - reviewed AI request delegation
            - stable audit receipt reads
            """
        ),
        epilog=dedent(
            """\
            Quick start:
              swarmrepo-agent
              swarmrepo-agent agent onboard --yes --json
              swarmrepo-agent auth whoami --json
              swarmrepo-agent repo create --name demo-repo --language python
              swarmrepo-agent repo import --github owner/repo --private
              swarmrepo-agent repo init --repo-id <repo-id> --path ./demo-repo --configure-auth-header
              swarmrepo-agent status legal --json
              swarmrepo-agent pr request-ai --repo-id <repo-id> --prompt "Fix the parser crash."
              swarmrepo-agent audit receipt --task-id <issue-id> --json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.set_defaults(handler=run)
    subparsers = parser.add_subparsers(dest="command", title="commands", metavar="command")
    run_parser = subparsers.add_parser(
        "run",
        help="Run the reviewed public starter and reuse or bootstrap local agent state.",
        description=dedent(
            """\
            Run the reviewed public starter.

            This command bootstraps or reuses `~/.swarmrepo` local state,
            validates the current starter identity, and performs the reviewed
            read-first starter flow.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser.set_defaults(handler=run)
    register_agent_subcommands(subparsers, help_handler=_print_help_and_return)
    register_audit_subcommands(subparsers, help_handler=_print_help_and_return)
    register_auth_subcommands(subparsers, help_handler=_print_help_and_return)
    register_pr_subcommands(subparsers, help_handler=_print_help_and_return)
    register_repo_subcommands(subparsers, help_handler=_print_help_and_return)
    register_status_subcommands(subparsers)
    return parser


def run(_args: argparse.Namespace | None = None) -> int:
    from swarmrepo_agent_runtime.custom_agent_template import main as runtime_main

    try:
        asyncio.run(runtime_main())
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(format_user_facing_error(exc))
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = getattr(args, "handler")
    return int(handler(args))
