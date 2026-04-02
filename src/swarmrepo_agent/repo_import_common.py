"""Shared helpers for the reviewed public `repo import` command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_IMPORT_MAX_FILES = 200
DEFAULT_IMPORT_MAX_FILE_BYTES = 128 * 1024


@dataclass(frozen=True, slots=True)
class ImportedSourceMaterial:
    """Normalized source material ready for reviewed repo creation."""

    source: str
    source_kind: str
    name_hint: str
    file_tree: dict[str, str]
    file_count: int
    inferred_languages: list[str]
    warnings: list[str] = field(default_factory=list)
    summary_extra: dict[str, Any] | None = None


def normalize_languages(values: list[str]) -> list[str]:
    """Normalize repeated or comma-separated language inputs."""

    normalized: list[str] = []
    for value in values:
        for item in value.split(","):
            language = item.strip()
            if language:
                normalized.append(language)

    deduped: list[str] = []
    seen: set[str] = set()
    for language in normalized:
        lowered = language.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(language)
    return deduped


def infer_import_name_from_git_url(git_url: str) -> str:
    """Derive a stable default repo name from one git URL or local git path."""

    candidate = git_url.rstrip("/").rsplit("/", 1)[-1]
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    return candidate or Path(git_url).name or "imported-repo"


def infer_import_name_from_archive_path(path: str | Path) -> str:
    """Derive a stable default repo name from one archive filename."""

    archive_path = Path(path)
    lower_name = archive_path.name.lower()
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".zip", ".tar"):
        if lower_name.endswith(suffix):
            return archive_path.name[: -len(suffix)] or archive_path.stem or "imported-archive"
    return archive_path.stem or "imported-archive"


__all__ = [
    "DEFAULT_IMPORT_MAX_FILES",
    "DEFAULT_IMPORT_MAX_FILE_BYTES",
    "ImportedSourceMaterial",
    "infer_import_name_from_archive_path",
    "infer_import_name_from_git_url",
    "normalize_languages",
]
