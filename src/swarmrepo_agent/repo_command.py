"""Reviewed public `repo` command surface for swarmrepo-agent."""

from __future__ import annotations

import argparse
from textwrap import dedent

from .repo_create import register_repo_create_subcommand
from .repo_import import register_repo_import_subcommand
from .repo_init import register_repo_init_subcommand


def register_repo_subcommands(
    subparsers: argparse._SubParsersAction,
    *,
    help_handler,
) -> None:
    """Register reviewed public repository commands."""

    repo_parser = subparsers.add_parser(
        "repo",
        help="Create and bind reviewed repositories through the stable public starter surface.",
        description=dedent(
            """\
            Reviewed public repository commands.

            Use `repo create` to create a new SwarmRepo repository container.
            Use `repo import` to ingest local, git, GitHub, or archive source
            material into one new independent reviewed repository.
            Use `repo init` to bind a local worktree to one reviewed remote and
            write local binding metadata into `.swarmrepo_platform/`.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent repo create --name demo-repo --language python
              swarmrepo-agent repo import --github owner/repo --private
              swarmrepo-agent repo init --repo-id <repo-id> --path ./demo-repo
              swarmrepo-agent repo init --repo-id <repo-id> --configure-auth-header --json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    repo_parser.set_defaults(handler=lambda _args, parser=repo_parser: help_handler(parser))
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command")

    register_repo_create_subcommand(repo_subparsers)
    register_repo_import_subcommand(repo_subparsers)
    register_repo_init_subcommand(repo_subparsers)


__all__ = ["register_repo_subcommands"]
