"""Local git helpers for reviewed public `repo` commands."""

from __future__ import annotations

import base64
from pathlib import Path
import subprocess


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable was not found on PATH.") from exc

    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip() or completed.stdout.strip() or "git command failed."
        )
    return completed


def ensure_worktree_path(path: str | Path) -> Path:
    """Create or reuse one local worktree directory."""

    worktree = Path(path).expanduser().resolve(strict=False)
    worktree.mkdir(parents=True, exist_ok=True)
    if not worktree.is_dir():
        raise RuntimeError(f"repo init path must resolve to a directory: {worktree}")
    return worktree


def is_git_repository(path: Path) -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(path),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def init_git_repository(path: Path, *, default_branch: str) -> bool:
    """Initialize one git repository when the target path is not already a worktree."""

    if is_git_repository(path):
        return False

    completed = subprocess.run(
        ["git", "init", "--initial-branch", default_branch],
        cwd=str(path),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode == 0:
        return True

    _run_git(["init"], cwd=path)
    _run_git(["symbolic-ref", "HEAD", f"refs/heads/{default_branch}"], cwd=path)
    return True


def get_remote_url(path: Path, *, remote_name: str) -> str | None:
    completed = subprocess.run(
        ["git", "remote", "get-url", remote_name],
        cwd=str(path),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def ensure_remote(path: Path, *, remote_name: str, remote_url: str, force_remote: bool) -> str:
    existing = get_remote_url(path, remote_name=remote_name)
    if existing is None:
        _run_git(["remote", "add", remote_name, remote_url], cwd=path)
        return "added"
    if existing == remote_url:
        return "unchanged"
    if not force_remote:
        raise RuntimeError(
            "Remote already exists with a different URL. Pass --force-remote to replace it."
        )
    _run_git(["remote", "set-url", remote_name, remote_url], cwd=path)
    return "updated"


def build_git_basic_auth_header(access_token: str) -> str:
    """Build the proactive Basic auth header used by reviewed Git Smart HTTP flows."""

    payload = base64.b64encode(f"x-access-token:{access_token}".encode("utf-8")).decode("ascii")
    return f"Basic {payload}"


def configure_http_extra_header(path: Path, *, header_value: str) -> None:
    _run_git(
        ["config", "--local", "http.extraHeader", f"Authorization: {header_value}"],
        cwd=path,
    )


def ensure_gitignore_entry(path: Path, *, entry: str) -> bool:
    """Ensure one literal line exists in the local repo `.gitignore`."""

    target = path / ".gitignore"
    if target.exists():
        content = target.read_text(encoding="utf-8")
        lines = content.splitlines()
        if entry in lines:
            return False
        suffix = "" if content.endswith(("\n", "\r")) or not content else "\n"
        target.write_text(f"{content}{suffix}{entry}\n", encoding="utf-8")
        return True

    target.write_text(f"{entry}\n", encoding="utf-8")
    return True


__all__ = [
    "build_git_basic_auth_header",
    "configure_http_extra_header",
    "ensure_gitignore_entry",
    "ensure_remote",
    "ensure_worktree_path",
    "get_remote_url",
    "init_git_repository",
    "is_git_repository",
]
