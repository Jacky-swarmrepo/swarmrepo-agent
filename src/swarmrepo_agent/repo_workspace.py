"""Repo-root reviewed local workspace metadata helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swarmrepo_agent_runtime.state import save_state_document


REPO_RUNTIME_DIRNAME = ".swarmrepo_platform"
REPO_BINDING_FILENAME = "repo_binding.json"


def repo_runtime_dir(path: str | Path) -> Path:
    """Return the repo-root private runtime directory."""

    return Path(path).expanduser().resolve(strict=False) / REPO_RUNTIME_DIRNAME


def repo_binding_path(path: str | Path) -> Path:
    """Return the reviewed repo-binding metadata path."""

    return repo_runtime_dir(path) / REPO_BINDING_FILENAME


def build_repo_binding_payload(
    *,
    repo_id: str,
    repo_name: str,
    default_branch: str,
    visibility: str,
    local_path: str,
    remote_name: str,
    remote_url: str,
    configured_auth_header: bool,
    state_dir: str,
    endpoint: str,
) -> dict[str, Any]:
    """Build the reviewed repo binding metadata payload."""

    return {
        "repo_id": repo_id,
        "repo_name": repo_name,
        "default_branch": default_branch,
        "visibility": visibility,
        "local_path": local_path,
        "remote_name": remote_name,
        "remote_url": remote_url,
        "configured_auth_header": configured_auth_header,
        "state_dir": state_dir,
        "endpoint": endpoint,
        "follow_up_commands": [
            f'swarmrepo-agent pr request-ai --repo-id {repo_id} --prompt "describe the requested change"',
            "swarmrepo-agent audit receipt --task-id <issue-id> --json",
        ],
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def save_repo_binding(path: str | Path, payload: dict[str, Any]) -> Path:
    """Persist repo-root reviewed binding metadata."""

    target = repo_binding_path(path)
    save_state_document(target, payload)
    return target


__all__ = [
    "REPO_BINDING_FILENAME",
    "REPO_RUNTIME_DIRNAME",
    "build_repo_binding_payload",
    "repo_binding_path",
    "repo_runtime_dir",
    "save_repo_binding",
]
