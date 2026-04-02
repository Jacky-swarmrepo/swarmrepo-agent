"""Repository import command for the reviewed public starter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from textwrap import dedent
from typing import Any, Mapping

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

from .client_context import apply_local_byok_context, resolve_local_byok_context
from .identity_bootstrap import ensure_identity
from .repo_import_archive import load_archive_source
from .repo_import_common import (
    DEFAULT_IMPORT_MAX_FILE_BYTES,
    DEFAULT_IMPORT_MAX_FILES,
    ImportedSourceMaterial,
    normalize_languages,
)
from .repo_import_git import load_git_source
from .repo_import_github import load_github_source
from .repo_import_tree import load_local_path_source


def register_repo_import_subcommand(repo_subparsers: argparse._SubParsersAction) -> None:
    """Register `swarmrepo-agent repo import`."""

    import_parser = repo_subparsers.add_parser(
        "import",
        help="Import local, git, GitHub, or archive source material into a new reviewed repository.",
        description=dedent(
            """\
            Import source material into one new reviewed SwarmRepo repository.

            Choose exactly one reviewed import mode:
            - `--local-path` for one local source directory
            - `--git-url` for one git clone source
            - `--github` for one GitHub repo slug or URL
            - `--archive` for one .zip or tar-based archive

            The command creates a new independent SwarmRepo repository from the
            imported source material. It preserves source provenance in the
            command result, but it does not create a live sync or mirror.
            """
        ),
        epilog=dedent(
            """\
            Examples:
              swarmrepo-agent repo import --local-path ./project-src
              swarmrepo-agent repo import --git-url https://example.com/demo.git --name imported-demo
              swarmrepo-agent repo import --github owner/repo --private
              swarmrepo-agent repo import --archive ./source-bundle.zip --json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source_group = import_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--local-path",
        default=None,
        help="Local directory to ingest as source material.",
    )
    source_group.add_argument(
        "--git-url",
        default=None,
        help="Git clone URL or local git path to ingest as source material.",
    )
    source_group.add_argument(
        "--github",
        default=None,
        help="GitHub slug or URL to ingest as source material.",
    )
    source_group.add_argument(
        "--archive",
        default=None,
        help="Archive path (.zip or tar-based) to ingest as source material.",
    )
    import_parser.add_argument(
        "--name",
        default=None,
        help="Optional reviewed repository name. Defaults to a source-derived name.",
    )
    import_parser.add_argument(
        "--language",
        action="append",
        dest="languages",
        default=[],
        help="Normalized language label. Repeat or pass comma-separated values to override inferred languages.",
    )
    import_parser.add_argument(
        "--description",
        default=None,
        help="Optional repository description for the created reviewed repo.",
    )
    import_parser.add_argument(
        "--default-branch",
        default="main",
        help="Protected default branch name for the created reviewed repo.",
    )
    visibility_group = import_parser.add_mutually_exclusive_group()
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
    import_parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden source files except for reviewed skipped runtime directories like .git and .swarmrepo_platform.",
    )
    import_parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_IMPORT_MAX_FILES,
        help=f"Maximum number of importable text files to ingest. Defaults to {DEFAULT_IMPORT_MAX_FILES}.",
    )
    import_parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_IMPORT_MAX_FILE_BYTES,
        help=f"Maximum size for each imported text file in bytes. Defaults to {DEFAULT_IMPORT_MAX_FILE_BYTES}.",
    )
    import_parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the local reviewed starter state directory.",
    )
    import_parser.add_argument(
        "--base-url",
        default=None,
        help="Override the SwarmRepo API base URL used for repo import.",
    )
    import_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the import payload as JSON.",
    )
    import_parser.set_defaults(handler=repo_import_command)


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


def _require_write_context(
    *,
    agent: Mapping[str, Any],
    credentials: Mapping[str, Any],
) -> dict[str, str | None]:
    context = resolve_local_byok_context(agent=agent, credentials=credentials)
    if not context["provider"]:
        raise RuntimeError(
            "repo import requires a provider. Set EXTERNAL_PROVIDER or persist one through starter state."
        )
    if not context["model"]:
        raise RuntimeError(
            "repo import requires a model. Set EXTERNAL_MODEL or persist one through starter state."
        )
    if not context["external_api_key"]:
        raise RuntimeError(
            "repo import requires EXTERNAL_API_KEY for reviewed source ingestion."
        )
    return context


def _load_source_material(args: argparse.Namespace) -> ImportedSourceMaterial:
    if args.local_path:
        return load_local_path_source(
            args.local_path,
            include_hidden=args.include_hidden,
            max_files=args.max_files,
            max_file_bytes=args.max_file_bytes,
        )
    if args.git_url:
        return load_git_source(
            args.git_url,
            include_hidden=args.include_hidden,
            max_files=args.max_files,
            max_file_bytes=args.max_file_bytes,
        )
    if args.github:
        return load_github_source(
            args.github,
            include_hidden=args.include_hidden,
            max_files=args.max_files,
            max_file_bytes=args.max_file_bytes,
        )
    if args.archive:
        return load_archive_source(
            args.archive,
            include_hidden=args.include_hidden,
            max_files=args.max_files,
            max_file_bytes=args.max_file_bytes,
        )
    raise RuntimeError("repo import requires one reviewed import mode.")


def _build_output_payload(
    *,
    agent: Any,
    repo: Any,
    state_dir: Path,
    source_material: ImportedSourceMaterial,
) -> dict[str, Any]:
    repo_payload = repo.model_dump(mode="json")
    data = {
        "repo": repo_payload,
        "import_summary": {
            "source": source_material.source,
            "source_kind": source_material.source_kind,
            "file_count": source_material.file_count,
            "languages": source_material.inferred_languages,
            **(source_material.summary_extra or {}),
        },
        "next_step_commands": [
            f"swarmrepo-agent repo init --repo-id {repo.id} --path ./{repo.name}",
            f'swarmrepo-agent pr request-ai --repo-id {repo.id} --prompt "describe the requested change"',
        ],
    }
    return {
        "command": "repo import",
        "state_dir": str(display_state_dir(state_dir)),
        "agent": {
            "id": str(agent.id),
            "name": agent.name,
        },
        "data": data,
        "warnings": source_material.warnings,
    }


def _render_text_result(payload: dict[str, Any]) -> None:
    data = payload["data"]
    repo = data["repo"]
    summary = data["import_summary"]
    languages = ", ".join(summary["languages"])
    print(f"Imported source material into repository {repo['name']} ({repo['id']}).")
    print(
        f"source_kind={summary['source_kind']} files={summary['file_count']} languages={languages}"
    )
    print(f"source={summary['source']}")
    print("Next steps:")
    for command in data["next_step_commands"]:
        print(f"- {command}")
    print(f"state_dir={payload['state_dir']}")
    for warning in payload["warnings"]:
        print(f"warning: {warning}")


async def _repo_import_async(args: argparse.Namespace) -> int:
    load_reviewed_dotenv()

    base_url = (args.base_url or os.getenv("SWARM_REPO_URL") or DEFAULT_SWARM_REPO_URL).rstrip("/")
    is_visible_to_humans = True if args.public else not args.private
    source_material = _load_source_material(args)

    async with SwarmClient(base_url=base_url) as client:
        me, state_dir, credentials, agent = await _resolve_active_identity(
            client,
            state_dir=args.state_dir,
        )
        apply_local_byok_context(client, agent=agent, credentials=credentials)
        _require_write_context(agent=agent, credentials=credentials)

        languages = normalize_languages(args.languages) or source_material.inferred_languages
        if not languages:
            raise RuntimeError(
                "repo import could not infer languages from the source material. Pass --language explicitly."
            )

        repo = await client.create_repo(
            name=args.name or source_material.name_hint,
            languages=languages,
            description=args.description,
            file_tree=source_material.file_tree,
            default_branch=args.default_branch,
            is_visible_to_humans=is_visible_to_humans,
        )

    payload = _build_output_payload(
        agent=me,
        repo=repo,
        state_dir=state_dir,
        source_material=ImportedSourceMaterial(
            source=source_material.source,
            source_kind=source_material.source_kind,
            name_hint=source_material.name_hint,
            file_tree=source_material.file_tree,
            file_count=source_material.file_count,
            inferred_languages=languages,
            warnings=source_material.warnings,
            summary_extra=source_material.summary_extra,
        ),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _render_text_result(payload)
    return 0


def repo_import_command(args: argparse.Namespace) -> int:
    """CLI handler for `swarmrepo-agent repo import`."""

    try:
        return asyncio.run(_repo_import_async(args))
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, SwarmSDKError) as exc:
        print(format_user_facing_error(exc))
        return 1


__all__ = ["register_repo_import_subcommand", "repo_import_command"]
