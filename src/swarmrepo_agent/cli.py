"""Stable reviewed starter entrypoints for swarmrepo-agent."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from ._version import __version__
from .repo_create import register_repo_subcommands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swarmrepo-agent",
        description="Run the reviewed public SwarmRepo-compatible agent starter.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser(
        "run",
        help="Run the reviewed public agent starter.",
    )
    run_parser.set_defaults(handler=run)
    register_repo_subcommands(subparsers)
    return parser


def run(_args: argparse.Namespace | None = None) -> int:
    from swarmrepo_agent_runtime.custom_agent_template import main as runtime_main

    try:
        asyncio.run(runtime_main())
    except KeyboardInterrupt:
        return 130
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = getattr(args, "handler", run)
    return int(handler(args))
