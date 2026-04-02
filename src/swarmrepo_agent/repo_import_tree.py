"""Local source-tree loading helpers for the reviewed public starter."""

from __future__ import annotations

from pathlib import Path

from .repo_import_common import (
    DEFAULT_IMPORT_MAX_FILE_BYTES,
    DEFAULT_IMPORT_MAX_FILES,
    ImportedSourceMaterial,
)


_SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".swarmrepo",
    ".swarmrepo_platform",
}


def _looks_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _should_skip(path: Path, *, include_hidden: bool) -> bool:
    if any(part in _SKIP_DIR_NAMES for part in path.parts):
        return True
    if not include_hidden and _looks_hidden(path):
        return True
    return False


def _infer_language_from_path(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    mapping = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".kt": "kotlin",
        ".swift": "swift",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".h": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".sql": "sql",
    }
    return mapping.get(suffix)


def _dedupe_languages(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(value)
    return deduped


def load_local_source_tree(
    path: str | Path,
    *,
    include_hidden: bool = False,
    max_files: int = DEFAULT_IMPORT_MAX_FILES,
    max_file_bytes: int = DEFAULT_IMPORT_MAX_FILE_BYTES,
) -> tuple[dict[str, str], int, list[str], list[str]]:
    """Load one UTF-8 source tree into the reviewed public file-tree shape."""

    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise RuntimeError(f"repo import local path does not exist: {root}")
    if not root.is_dir():
        raise RuntimeError(f"repo import local path must be a directory: {root}")

    file_tree: dict[str, str] = {}
    warnings: list[str] = []
    inferred_languages: list[str] = []

    files = sorted(candidate for candidate in root.rglob("*") if candidate.is_file())
    for candidate in files:
        relative = candidate.relative_to(root)
        if _should_skip(relative, include_hidden=include_hidden):
            continue
        if candidate.is_symlink():
            warnings.append(f"Skipped symlinked file: {relative.as_posix()}")
            continue
        if len(file_tree) >= max_files:
            raise RuntimeError(
                f"repo import exceeded max_files={max_files}. Narrow the source or raise the limit."
            )

        stat = candidate.stat()
        if stat.st_size > max_file_bytes:
            warnings.append(
                f"Skipped oversized file: {relative.as_posix()} ({stat.st_size} bytes > {max_file_bytes})"
            )
            continue

        raw = candidate.read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            warnings.append(f"Skipped non-UTF-8 file: {relative.as_posix()}")
            continue

        relative_path = relative.as_posix()
        file_tree[relative_path] = content
        inferred = _infer_language_from_path(relative_path)
        if inferred:
            inferred_languages.append(inferred)

    if not file_tree:
        raise RuntimeError("repo import did not produce any importable UTF-8 text files.")

    return file_tree, len(file_tree), _dedupe_languages(inferred_languages), warnings


def load_local_path_source(
    path: str,
    *,
    include_hidden: bool = False,
    max_files: int = DEFAULT_IMPORT_MAX_FILES,
    max_file_bytes: int = DEFAULT_IMPORT_MAX_FILE_BYTES,
) -> ImportedSourceMaterial:
    """Load one local-path import source."""

    resolved = Path(path).expanduser().resolve()
    file_tree, file_count, inferred_languages, warnings = load_local_source_tree(
        resolved,
        include_hidden=include_hidden,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
    )
    return ImportedSourceMaterial(
        source=str(resolved),
        source_kind="local_path",
        name_hint=resolved.name or "imported-repo",
        file_tree=file_tree,
        file_count=file_count,
        inferred_languages=inferred_languages,
        warnings=warnings,
    )


__all__ = ["load_local_path_source", "load_local_source_tree"]
