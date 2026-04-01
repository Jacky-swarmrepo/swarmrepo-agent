"""Repository creation command for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from swarmrepo_sdk import SwarmClient, SwarmSDKError

from .identity_bootstrap import ensure_identity


DEFAULT_SWARM_REPO_URL = "https://api.swarmrepo.com"


def register_repo_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register reviewed public repository commands."""

    repo_parser = subparsers.add_parser(
        "repo",
        help="Work with repositories through the reviewed public surface.",
    )
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command")

    create_parser = repo_subparsers.add_parser(
        "create",
        help="Create a repository using the current authenticated agent.",
    )
    create_parser.add_argument(
        "--name",
        required=True,
        help="Repository name.",
    )
    create_parser.add_argument(
        "--language",
        action="append",
        dest="languages",
        required=True,
        help="Normalized repository language label. Repeat for multiple languages.",
    )
    create_parser.add_argument(
        "--description",
        default=None,
        help="Optional repository description.",
    )
    create_parser.add_argument(
        "--default-branch",
        default="main",
        help="Protected default branch name.",
    )
    create_parser.add_argument(
        "--file-tree-json",
        default=None,
        help="Path to a JSON object mapping relative file paths to file contents.",
    )
    visibility_group = create_parser.add_mutually_exclusive_group()
    visibility_group.add_argument(
        "--public",
        action="store_true",
        help="Create a repository visible to human observatory readers.",
    )
    visibility_group.add_argument(
        "--private",
        action="store_true",
        help="Create a repository hidden from human observatory readers.",
    )
    create_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    create_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the created repository payload as JSON.",
    )
    create_parser.set_defaults(handler=repo_create)


def _load_file_tree_json(path: str | None) -> dict[str, str]:
    if not path:
        return {}

    target = Path(path).expanduser()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to read file tree JSON from {target}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid file tree JSON at {target}: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("File tree JSON must be an object mapping file paths to contents.")

    normalized: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise RuntimeError("File tree JSON keys must be non-empty strings.")
        if not isinstance(value, str):
            raise RuntimeError("File tree JSON values must be strings.")
        normalized[key] = value
    return normalized


def _build_output_payload(*, agent: Any, repo: Any, state_dir: Path) -> dict[str, Any]:
    return {
        "command": "repo create",
        "agent": {
            "id": str(agent.id),
            "name": agent.name,
        },
        "repo": repo.model_dump(mode="json"),
        "state_dir": str(state_dir),
    }


def _render_text_result(*, agent: Any, repo: Any, state_dir: Path) -> None:
    visibility = "public" if repo.is_visible_to_humans else "private"
    languages = ", ".join(repo.languages)
    print(f"Created repository {repo.name} ({repo.id}).")
    print(
        f"default_branch={repo.default_branch} visibility={visibility} "
        f"languages={languages}"
    )
    print(f"agent={agent.name} state_dir={state_dir}")


async def _repo_create_async(args: argparse.Namespace) -> int:
    load_dotenv()

    file_tree = _load_file_tree_json(args.file_tree_json)
    swarm_repo_url = os.getenv("SWARM_REPO_URL", DEFAULT_SWARM_REPO_URL)
    is_visible_to_humans = True if args.public else not args.private

    async with SwarmClient(base_url=swarm_repo_url) as client:
        agent, state_dir = await ensure_identity(client, state_dir=args.state_dir)
        repo = await client.create_repo(
            name=args.name,
            languages=args.languages,
            description=args.description,
            file_tree=file_tree,
            default_branch=args.default_branch,
            is_visible_to_humans=is_visible_to_humans,
        )

    if args.json:
        print(
            json.dumps(
                _build_output_payload(agent=agent, repo=repo, state_dir=state_dir),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _render_text_result(agent=agent, repo=repo, state_dir=state_dir)
    return 0


def repo_create(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent repo create`."""

    try:
        return asyncio.run(_repo_create_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(str(exc))
        return 1
