"""Reviewed text attachment helpers for public PR request commands."""

from __future__ import annotations

from pathlib import Path


MAX_ATTACHMENT_BYTES = 32 * 1024


def load_optional_text_file(
    path: str | None,
    *,
    label: str,
    max_bytes: int = MAX_ATTACHMENT_BYTES,
) -> str | None:
    """Load one optional UTF-8 text attachment from disk."""

    if not path:
        return None

    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise RuntimeError(f"{label} file does not exist: {file_path}")
    if not file_path.is_file():
        raise RuntimeError(f"{label} path must be a file: {file_path}")

    raw = file_path.read_bytes()
    if len(raw) > max_bytes:
        raise RuntimeError(f"{label} file exceeds max_bytes={max_bytes}: {file_path}")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{label} file must be UTF-8 text: {file_path}") from exc


__all__ = ["MAX_ATTACHMENT_BYTES", "load_optional_text_file"]
