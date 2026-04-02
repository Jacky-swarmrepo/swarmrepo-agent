"""Local repo binding command for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
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
from swarmrepo_agent_runtime.user_errors import format_user_facing_error

from .client_context import apply_local_byok_context
from .identity_bootstrap import ensure_identity
from .repo_git_local import (
    build_git_basic_auth_header,
    configure_http_extra_header,
    ensure_gitignore_entry,
    ensure_remote,
    ensure_worktree_path,
    get_remote_url,
    init_git_repository,
)
from .repo_workspace import build_repo_binding_payload, save_repo_binding


def register_repo_init_subcommand(repo_subparsers: argparse._SubParsersAction) -> None:
    """Register `swarmrepo-agent repo init`."""

    init_parser = repo_subparsers.add_parser(
        "init",
        help="Bind one local worktree to a reviewed SwarmRepo repository.",
        description=dedent(
            """\
            Bind one local worktree to a reviewed SwarmRepo repository.

            `repo init` creates or reuses a local git worktree, configures one
            Git Smart HTTP remote for the reviewed hosted repo, writes
            `.swarmrepo_platform/repo_binding.json`, and optionally configures a
            local proactive git auth header from the current access token.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent repo init --repo-id <repo-id>
              swarmrepo-agent repo init --repo-id <repo-id> --path ./demo-repo
              swarmrepo-agent repo init --repo-id <repo-id> --path ./demo-repo --configure-auth-header --json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    init_parser.add_argument(
        "--repo-id",
        required=True,
        help="Repository identifier to bind to the local worktree.",
    )
    init_parser.add_argument(
        "--path",
        default=".",
        help="Local directory to initialize or bind. Defaults to the current directory.",
    )
    init_parser.add_argument(
        "--remote-name",
        default="origin",
        help="Local git remote name to create or update.",
    )
    init_parser.add_argument(
        "--force-remote",
        action="store_true",
        help="Replace an existing remote when it already points to a different URL.",
    )
    init_parser.add_argument(
        "--configure-auth-header",
        action="store_true",
        help="Configure one local proactive git Authorization header from the saved access token.",
    )
    init_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    init_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for repo binding.",
    )
    init_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the repo-binding payload as JSON.",
    )
    init_parser.set_defaults(handler=repo_init_command)


async def _resolve_active_identity(
    client: SwarmClient,
    *,
    state_dir: str | None,
) -> tuple[Any, Path, dict[str, Any], dict[str, Any]]:
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


def _build_git_clone_url(*, base_url: str, repo_id: str) -> str:
    return f"{base_url.rstrip('/')}/git/{repo_id}.git"


def _build_output_payload(
    *,
    repo: Any,
    state_dir: Path,
    worktree: Path,
    remote_name: str,
    remote_url: str,
    remote_action: str,
    created_git_repo: bool,
    configured_auth_header: bool,
    gitignore_updated: bool,
    binding_path_on_disk: Path,
    endpoint: str,
) -> dict[str, Any]:
    visibility = "public" if repo.is_visible_to_humans else "private"
    return {
        "command": "repo init",
        "state_dir": str(display_state_dir(state_dir)),
        "data": {
            "repo_id": str(repo.id),
            "repo_name": repo.name,
            "default_branch": repo.default_branch,
            "repo_visibility": visibility,
            "path": str(worktree),
            "remote_name": remote_name,
            "remote_url": remote_url,
            "remote_action": remote_action,
            "created_git_repo": created_git_repo,
            "configured_auth_header": configured_auth_header,
            "gitignore_updated": gitignore_updated,
            "binding_path": str(binding_path_on_disk),
            "endpoint": endpoint,
        },
    }


def _render_text_result(
    *,
    payload: dict[str, Any],
    warnings: list[str],
) -> None:
    data = payload["data"]
    print("Initialized local repository binding.")
    print(
        f"path={data['path']} remote={data['remote_name']} -> {data['remote_url']}"
    )
    print(
        f"default_branch={data['default_branch']} visibility={data['repo_visibility']} "
        f"auth_header={'yes' if data['configured_auth_header'] else 'no'}"
    )
    print(f"binding={data['binding_path']}")
    print(f"state_dir={payload['state_dir']}")
    for warning in warnings:
        print(f"warning: {warning}")


async def _repo_init_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")
    warnings: list[str] = []

    async with SwarmClient(base_url=base_url) as client:
        _me, state_dir, credentials, agent = await _resolve_active_identity(
            client,
            state_dir=args.state_dir,
        )
        apply_local_byok_context(client, agent=agent, credentials=credentials)
        repo = await client.get_repo_detail(args.repo_id, auth=True)

    worktree = ensure_worktree_path(args.path)
    created_git_repo = init_git_repository(worktree, default_branch=str(repo.default_branch or "main"))
    remote_url = _build_git_clone_url(base_url=base_url, repo_id=str(repo.id))
    remote_action = ensure_remote(
        worktree,
        remote_name=args.remote_name,
        remote_url=remote_url,
        force_remote=bool(args.force_remote),
    )
    current_remote_url = get_remote_url(worktree, remote_name=args.remote_name) or remote_url

    access_token = str(credentials.get("access_token") or "").strip()
    configured_auth_header = False
    if args.configure_auth_header:
        if not access_token:
            raise RuntimeError(
                "repo init --configure-auth-header requires a saved local access token."
            )
        configure_http_extra_header(
            worktree,
            header_value=build_git_basic_auth_header(access_token),
        )
        configured_auth_header = True
    else:
        warnings.append(
            "No local git auth header was configured. Private fetch or push may require manual auth setup."
        )

    gitignore_updated = ensure_gitignore_entry(worktree, entry=".swarmrepo_platform/")
    binding_doc = build_repo_binding_payload(
        repo_id=str(repo.id),
        repo_name=repo.name,
        default_branch=str(repo.default_branch or "main"),
        visibility="public" if repo.is_visible_to_humans else "private",
        local_path=str(worktree),
        remote_name=args.remote_name,
        remote_url=current_remote_url,
        configured_auth_header=configured_auth_header,
        state_dir=str(display_state_dir(state_dir)),
        endpoint=base_url,
    )
    binding_path_on_disk = save_repo_binding(worktree, binding_doc)

    payload = _build_output_payload(
        repo=repo,
        state_dir=state_dir,
        worktree=worktree,
        remote_name=args.remote_name,
        remote_url=current_remote_url,
        remote_action=remote_action,
        created_git_repo=created_git_repo,
        configured_auth_header=configured_auth_header,
        gitignore_updated=gitignore_updated,
        binding_path_on_disk=binding_path_on_disk,
        endpoint=base_url,
    )
    payload["warnings"] = warnings

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _render_text_result(payload=payload, warnings=warnings)
    return 0


def repo_init_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent repo init`."""

    try:
        return asyncio.run(_repo_init_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(format_user_facing_error(exc))
        return 1


__all__ = ["register_repo_init_subcommand", "repo_init_command"]
