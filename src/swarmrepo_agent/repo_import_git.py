"""Git-backed import helpers for the reviewed public starter."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile

from .repo_import_common import (
    DEFAULT_IMPORT_MAX_FILE_BYTES,
    DEFAULT_IMPORT_MAX_FILES,
    ImportedSourceMaterial,
    infer_import_name_from_git_url,
)
from .repo_import_tree import load_local_source_tree


def clone_git_source(git_url: str, *, destination: Path) -> None:
    """Clone one reviewed git source into a temporary directory."""

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(destination)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("repo import requires git to be installed and available on PATH.") from exc

    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip() or completed.stdout.strip() or "git clone failed."
        )


def load_git_source(
    git_url: str,
    *,
    include_hidden: bool = False,
    max_files: int = DEFAULT_IMPORT_MAX_FILES,
    max_file_bytes: int = DEFAULT_IMPORT_MAX_FILE_BYTES,
    source: str | None = None,
    source_kind: str = "git_url",
    name_hint: str | None = None,
    warnings: list[str] | None = None,
    summary_extra: dict | None = None,
) -> ImportedSourceMaterial:
    """Clone and normalize one git-backed source into importable file content."""

    with tempfile.TemporaryDirectory(prefix="swarmrepo-agent-import-git-") as temp_dir:
        clone_root = Path(temp_dir) / "clone"
        clone_git_source(git_url, destination=clone_root)
        file_tree, file_count, inferred_languages, clone_warnings = load_local_source_tree(
            clone_root,
            include_hidden=include_hidden,
            max_files=max_files,
            max_file_bytes=max_file_bytes,
        )

    combined_warnings = list(warnings or [])
    combined_warnings.extend(clone_warnings)
    combined_warnings.append(
        "repo import clones the source repository only to ingest file contents as reviewed workflow input."
    )
    return ImportedSourceMaterial(
        source=source or git_url,
        source_kind=source_kind,
        name_hint=name_hint or infer_import_name_from_git_url(git_url),
        file_tree=file_tree,
        file_count=file_count,
        inferred_languages=inferred_languages,
        warnings=combined_warnings,
        summary_extra=summary_extra,
    )


__all__ = ["clone_git_source", "load_git_source"]
