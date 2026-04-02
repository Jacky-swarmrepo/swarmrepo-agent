"""Archive-backed import helpers for the reviewed public starter."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import tarfile
import tempfile
import zipfile

from .repo_import_common import (
    DEFAULT_IMPORT_MAX_FILE_BYTES,
    DEFAULT_IMPORT_MAX_FILES,
    ImportedSourceMaterial,
    infer_import_name_from_archive_path,
)
from .repo_import_tree import load_local_source_tree


def _normalize_archive_member(name: str) -> PurePosixPath | None:
    candidate = PurePosixPath(name)
    if not candidate.parts:
        return None
    if candidate.is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    return candidate


def _write_member(destination: Path, relative_path: PurePosixPath, content: bytes) -> None:
    target = destination.joinpath(*relative_path.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _extract_zip_archive(
    archive_path: Path,
    *,
    destination: Path,
    max_files: int,
    max_file_bytes: int,
) -> list[str]:
    warnings: list[str] = []
    accepted_files = 0
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            relative_path = _normalize_archive_member(member.filename)
            if relative_path is None:
                warnings.append(f"Skipped unsafe archive member: {member.filename}")
                continue
            if accepted_files >= max_files:
                raise RuntimeError(
                    f"archive import exceeded max_files={max_files}. Narrow the archive or raise the limit."
                )
            if member.file_size > max_file_bytes:
                warnings.append(
                    f"Skipped oversized archive member: {relative_path.as_posix()} ({member.file_size} bytes > {max_file_bytes})"
                )
                continue
            content = archive.read(member)
            _write_member(destination, relative_path, content)
            accepted_files += 1
    return warnings


def _extract_tar_archive(
    archive_path: Path,
    *,
    destination: Path,
    max_files: int,
    max_file_bytes: int,
) -> list[str]:
    warnings: list[str] = []
    accepted_files = 0
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            relative_path = _normalize_archive_member(member.name)
            if relative_path is None:
                warnings.append(f"Skipped unsafe archive member: {member.name}")
                continue
            if member.issym() or member.islnk():
                warnings.append(f"Skipped linked archive member: {relative_path.as_posix()}")
                continue
            if not member.isfile():
                warnings.append(f"Skipped unsupported archive member: {relative_path.as_posix()}")
                continue
            if accepted_files >= max_files:
                raise RuntimeError(
                    f"archive import exceeded max_files={max_files}. Narrow the archive or raise the limit."
                )
            if member.size > max_file_bytes:
                warnings.append(
                    f"Skipped oversized archive member: {relative_path.as_posix()} ({member.size} bytes > {max_file_bytes})"
                )
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                warnings.append(f"Skipped unreadable archive member: {relative_path.as_posix()}")
                continue
            with extracted:
                content = extracted.read()
            _write_member(destination, relative_path, content)
            accepted_files += 1
    return warnings


def _extract_archive_to_directory(
    archive_path: Path,
    *,
    destination: Path,
    max_files: int,
    max_file_bytes: int,
) -> list[str]:
    try:
        if zipfile.is_zipfile(archive_path):
            return _extract_zip_archive(
                archive_path,
                destination=destination,
                max_files=max_files,
                max_file_bytes=max_file_bytes,
            )
        if tarfile.is_tarfile(archive_path):
            return _extract_tar_archive(
                archive_path,
                destination=destination,
                max_files=max_files,
                max_file_bytes=max_file_bytes,
            )
    except (OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise RuntimeError(f"archive import failed to read archive: {archive_path}") from exc

    raise RuntimeError("archive import supports .zip and tar-based archives only.")


def load_archive_source(
    path: str,
    *,
    include_hidden: bool = False,
    max_files: int = DEFAULT_IMPORT_MAX_FILES,
    max_file_bytes: int = DEFAULT_IMPORT_MAX_FILE_BYTES,
) -> ImportedSourceMaterial:
    """Extract and normalize one archive-backed import source."""

    archive_path = Path(path).expanduser().resolve()
    if not archive_path.exists():
        raise RuntimeError(f"archive import path does not exist: {archive_path}")
    if not archive_path.is_file():
        raise RuntimeError(f"archive import path must be a file: {archive_path}")

    with tempfile.TemporaryDirectory(prefix="swarmrepo-agent-import-archive-") as temp_dir:
        extracted_root = Path(temp_dir) / "archive"
        extracted_root.mkdir(parents=True, exist_ok=True)
        archive_warnings = _extract_archive_to_directory(
            archive_path,
            destination=extracted_root,
            max_files=max_files,
            max_file_bytes=max_file_bytes,
        )
        file_tree, file_count, inferred_languages, extracted_warnings = load_local_source_tree(
            extracted_root,
            include_hidden=include_hidden,
            max_files=max_files,
            max_file_bytes=max_file_bytes,
        )

    warnings = list(archive_warnings)
    warnings.extend(extracted_warnings)
    warnings.append(
        "archive import extracts source material only to ingest file contents as reviewed workflow input."
    )
    return ImportedSourceMaterial(
        source=str(archive_path),
        source_kind="archive",
        name_hint=infer_import_name_from_archive_path(archive_path),
        file_tree=file_tree,
        file_count=file_count,
        inferred_languages=inferred_languages,
        warnings=warnings,
    )


__all__ = ["load_archive_source"]
