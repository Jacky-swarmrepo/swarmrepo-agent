"""GitHub normalization helpers for reviewed public repo import."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from .repo_import_common import DEFAULT_IMPORT_MAX_FILE_BYTES, DEFAULT_IMPORT_MAX_FILES
from .repo_import_git import load_git_source


_GITHUB_HOSTS = {"github.com", "www.github.com"}
_SLUG_PATTERN = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)
_SSH_PATTERN = re.compile(
    r"^git@github\.com:(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)


@dataclass(frozen=True, slots=True)
class NormalizedGitHubSource:
    """One reviewed normalized GitHub repository source."""

    input_value: str
    owner: str
    repo: str
    slug: str
    repository_url: str
    clone_url: str


def _normalize_slug(owner: str, repo: str, *, input_value: str) -> NormalizedGitHubSource:
    normalized_repo = repo[:-4] if repo.endswith(".git") else repo
    if not owner or not normalized_repo:
        raise RuntimeError("GitHub import requires an owner/repo identifier.")
    slug = f"{owner}/{normalized_repo}"
    repository_url = f"https://github.com/{slug}"
    return NormalizedGitHubSource(
        input_value=input_value,
        owner=owner,
        repo=normalized_repo,
        slug=slug,
        repository_url=repository_url,
        clone_url=f"{repository_url}.git",
    )


def normalize_github_source(value: str) -> NormalizedGitHubSource:
    """Normalize one GitHub slug, URL, or SSH source into canonical form."""

    stripped = value.strip()
    if not stripped:
        raise RuntimeError("GitHub import requires a non-empty owner/repo or GitHub URL.")

    slug_match = _SLUG_PATTERN.match(stripped)
    if slug_match:
        return _normalize_slug(
            slug_match.group("owner"),
            slug_match.group("repo"),
            input_value=value,
        )

    ssh_match = _SSH_PATTERN.match(stripped)
    if ssh_match:
        return _normalize_slug(
            ssh_match.group("owner"),
            ssh_match.group("repo"),
            input_value=value,
        )

    parsed = urlparse(stripped)
    if parsed.scheme in {"http", "https", "ssh"}:
        if (parsed.hostname or "").lower() not in _GITHUB_HOSTS:
            raise RuntimeError("GitHub import accepts only github.com repository URLs.")
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) != 2:
            raise RuntimeError("GitHub import currently supports repository root URLs only.")
        return _normalize_slug(
            path_parts[0],
            path_parts[1],
            input_value=value,
        )

    raise RuntimeError(
        "GitHub import expects owner/repo, https://github.com/owner/repo, or git@github.com:owner/repo.git."
    )


def load_github_source(
    value: str,
    *,
    include_hidden: bool = False,
    max_files: int = DEFAULT_IMPORT_MAX_FILES,
    max_file_bytes: int = DEFAULT_IMPORT_MAX_FILE_BYTES,
):
    """Normalize and load one GitHub import source."""

    github = normalize_github_source(value)
    return load_git_source(
        github.clone_url,
        include_hidden=include_hidden,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        source=github.repository_url,
        source_kind="github",
        name_hint=github.repo,
        warnings=[
            "github import normalizes the source into one reviewed github.com clone URL and ingests it as workflow input."
        ],
        summary_extra={
            "github": {
                "input": github.input_value,
                "slug": github.slug,
                "owner": github.owner,
                "repo": github.repo,
                "repository_url": github.repository_url,
                "clone_url": github.clone_url,
            }
        },
    )


__all__ = ["NormalizedGitHubSource", "load_github_source", "normalize_github_source"]
