"""Shared helpers for reviewed public `pr request-ai` commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from .legal_evidence import build_legal_state_follow_up_lines


ISSUE_DESCRIPTION_LIMIT = 4096
ISSUE_TITLE_LIMIT = 256
DEFAULT_REQUEST_TITLE = "AI change request"
ISSUE_REFERENCE_WARNING = (
    "The issue acts as the durable delegation object until explicit public PR-request resources exist."
)
LINKED_ISSUE_WARNING = (
    "Supplemental existing-issue inputs were persisted by creating a linked delegation issue."
)


def build_receipt_hint(*, issue_id: str | None) -> dict[str, str | None]:
    """Build the reviewed stable receipt hint for one delegation issue."""

    return {
        "kind": "task_id",
        "value": issue_id,
        "command": f"swarmrepo-agent audit receipt --task-id {issue_id}" if issue_id else None,
    }


def build_navigation_hints(*, issue_id: str | None) -> list[dict[str, str]]:
    """Build stable follow-up command hints for one accepted request."""

    receipt_command = (
        f"swarmrepo-agent audit receipt --task-id {issue_id}"
        if issue_id
        else "swarmrepo-agent audit receipt --task-id <issue-id>"
    )
    return [
        {
            "kind": "canonical_receipt",
            "command": receipt_command,
            "reason": "Read the durable task receipt created for this AI request.",
        },
        {
            "kind": "status",
            "command": "swarmrepo-agent status",
            "reason": "Inspect the local starter auth, legal, and agent readiness.",
        },
        {
            "kind": "status_legal",
            "command": "swarmrepo-agent status legal --json",
            "reason": "Inspect the authenticated remote legal evidence companion read.",
        },
    ]


def normalize_title(title: str) -> str:
    """Normalize one user-facing issue title into the public length budget."""

    collapsed = " ".join(title.strip().split())
    if not collapsed:
        return DEFAULT_REQUEST_TITLE
    if len(collapsed) <= ISSUE_TITLE_LIMIT:
        return collapsed
    return collapsed[: ISSUE_TITLE_LIMIT - 3].rstrip() + "..."


def truncate_description(description: str, *, warnings: list[str]) -> str:
    """Clamp issue descriptions to the reviewed public API limit."""

    if len(description) <= ISSUE_DESCRIPTION_LIMIT:
        return description
    warnings.append(
        f"Request description exceeded {ISSUE_DESCRIPTION_LIMIT} characters and was truncated."
    )
    return description[: ISSUE_DESCRIPTION_LIMIT - 3].rstrip() + "..."


def normalize_optional_path(path: str | None) -> str | None:
    """Render one optional filesystem path as an absolute string."""

    if not path:
        return None
    return str(Path(path).expanduser().resolve())


def has_existing_issue_supplemental_inputs(args: argparse.Namespace) -> bool:
    """Return whether an existing-issue request carries extra delegation context."""

    return bool(
        args.diff_file
        or args.context_file
        or args.changed_files_only
        or args.base_branch
    )


def build_prompt_request_description(
    args: argparse.Namespace,
    *,
    context_text: str | None,
    diff_text: str | None,
    warnings: list[str],
) -> str:
    """Build the durable prompt-backed issue description."""

    sections = [
        "Requested via swarmrepo-agent pr request-ai.",
        "",
        "Prompt:",
        args.prompt.strip(),
    ]
    metadata_lines: list[str] = []
    if args.base_branch:
        metadata_lines.append(f"- base_branch: {args.base_branch}")
    if args.changed_files_only:
        metadata_lines.append("- changed_files_only: true")
    if metadata_lines:
        sections.extend(["", "Request metadata:", *metadata_lines])
    if context_text:
        sections.extend(["", "Additional context:", context_text.strip()])
    if diff_text:
        sections.extend(["", "Suggested diff input:", diff_text.strip()])
    return truncate_description("\n".join(sections), warnings=warnings)


def build_linked_issue_request_title(source_issue: Mapping[str, Any]) -> str:
    """Build the reviewed delegation title for one source issue."""

    source_title = str(source_issue.get("title") or "").strip()
    if source_title:
        return normalize_title(f"AI change request: {source_title}")
    return normalize_title(f"AI change request for issue {source_issue.get('id', '(unknown)')}")


def build_linked_issue_request_description(
    args: argparse.Namespace,
    *,
    source_issue: Mapping[str, Any],
    context_text: str | None,
    diff_text: str | None,
    warnings: list[str],
) -> str:
    """Build the durable linked-delegation issue description."""

    sections = [
        "Requested via swarmrepo-agent pr request-ai.",
        "",
        "Delegation mode:",
        "linked_issue_request",
        "",
        "Source issue:",
        f"- issue_id: {source_issue.get('id', '(unknown)')}",
        f"- title: {source_issue.get('title') or '(missing)'}",
        f"- status: {source_issue.get('status') or '(missing)'}",
    ]
    metadata_lines: list[str] = []
    if args.base_branch:
        metadata_lines.append(f"- base_branch: {args.base_branch}")
    if args.changed_files_only:
        metadata_lines.append("- changed_files_only: true")
    if metadata_lines:
        sections.extend(["", "Request metadata:", *metadata_lines])
    if context_text:
        sections.extend(["", "Additional context:", context_text.strip()])
    if diff_text:
        sections.extend(["", "Suggested diff input:", diff_text.strip()])
    return truncate_description("\n".join(sections), warnings=warnings)


def _legal_evidence_line(
    current_agent_legal_evidence_summary: Mapping[str, Any] | None,
) -> str:
    if current_agent_legal_evidence_summary is None:
        return "Current legal evidence: unavailable"
    return (
        "Current legal evidence: complete"
        if current_agent_legal_evidence_summary.get("evidence_complete")
        else "Current legal evidence: partial"
    )


def _base_result_data(
    *,
    repo_id: str,
    issue_id: str | None,
    current_agent_legal_evidence_summary: Mapping[str, Any] | None,
    current_agent_legal_error: Mapping[str, str] | None,
) -> dict[str, Any]:
    return {
        "request_status": "accepted",
        "repo_id": repo_id,
        "receipt_hint": build_receipt_hint(issue_id=issue_id),
        "navigation_hints": build_navigation_hints(issue_id=issue_id),
        "current_agent_legal_evidence_summary": current_agent_legal_evidence_summary,
        "current_agent_legal_error": current_agent_legal_error,
    }


def build_prompt_result(
    *,
    repo_id: str,
    issue: Mapping[str, Any],
    normalized_request: Mapping[str, Any],
    current_agent_legal_evidence_summary: Mapping[str, Any] | None,
    current_agent_legal_error: Mapping[str, str] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Build the stable payload and text lines for prompt-backed requests."""

    issue_id = str(issue.get("id")) if issue.get("id") else None
    data = _base_result_data(
        repo_id=repo_id,
        issue_id=issue_id,
        current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
        current_agent_legal_error=current_agent_legal_error,
    )
    data.update(
        {
            "request_mode": "prompt_issue",
            "issue": issue,
            "normalized_request": dict(normalized_request),
        }
    )
    return data, [
        "AI change request accepted.",
        "Delegation mode: prompt_issue",
        f"Issue ID: {issue.get('id', '(unknown)')}",
        f"Repo ID: {repo_id}",
        f"Audit hint: swarmrepo-agent audit receipt --task-id {issue.get('id', '(unknown)')}",
        _legal_evidence_line(current_agent_legal_evidence_summary),
        *build_legal_state_follow_up_lines(),
    ]


def build_existing_issue_result(
    *,
    repo_id: str,
    issue: Mapping[str, Any],
    current_agent_legal_evidence_summary: Mapping[str, Any] | None,
    current_agent_legal_error: Mapping[str, str] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Build the stable payload and text lines for existing-issue requests."""

    issue_id = str(issue.get("id")) if issue.get("id") else None
    data = _base_result_data(
        repo_id=repo_id,
        issue_id=issue_id,
        current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
        current_agent_legal_error=current_agent_legal_error,
    )
    data.update(
        {
            "request_mode": "existing_issue",
            "issue": issue,
            "normalized_request": {
                "repo_id": repo_id,
                "issue_id": issue.get("id"),
            },
        }
    )
    return data, [
        "AI change request accepted.",
        "Delegation mode: existing_issue",
        f"Issue ID: {issue.get('id', '(unknown)')}",
        f"Repo ID: {repo_id}",
        f"Audit hint: swarmrepo-agent audit receipt --task-id {issue.get('id', '(unknown)')}",
        _legal_evidence_line(current_agent_legal_evidence_summary),
        *build_legal_state_follow_up_lines(),
    ]


def build_linked_issue_result(
    *,
    repo_id: str,
    source_issue: Mapping[str, Any],
    issue: Mapping[str, Any],
    normalized_request: Mapping[str, Any],
    current_agent_legal_evidence_summary: Mapping[str, Any] | None,
    current_agent_legal_error: Mapping[str, str] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Build the stable payload and text lines for linked-issue requests."""

    issue_id = str(issue.get("id")) if issue.get("id") else None
    data = _base_result_data(
        repo_id=repo_id,
        issue_id=issue_id,
        current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
        current_agent_legal_error=current_agent_legal_error,
    )
    data.update(
        {
            "request_mode": "linked_issue_request",
            "source_issue": source_issue,
            "issue": issue,
            "normalized_request": dict(normalized_request),
        }
    )
    return data, [
        "AI change request accepted.",
        "Delegation mode: linked_issue_request",
        f"Source issue ID: {source_issue.get('id', '(unknown)')}",
        f"Delegation issue ID: {issue.get('id', '(unknown)')}",
        f"Repo ID: {repo_id}",
        f"Audit hint: swarmrepo-agent audit receipt --task-id {issue.get('id', '(unknown)')}",
        _legal_evidence_line(current_agent_legal_evidence_summary),
        *build_legal_state_follow_up_lines(),
    ]


__all__ = [
    "DEFAULT_REQUEST_TITLE",
    "ISSUE_REFERENCE_WARNING",
    "LINKED_ISSUE_WARNING",
    "build_existing_issue_result",
    "build_linked_issue_request_description",
    "build_linked_issue_request_title",
    "build_linked_issue_result",
    "build_navigation_hints",
    "build_prompt_request_description",
    "build_prompt_result",
    "build_receipt_hint",
    "has_existing_issue_supplemental_inputs",
    "normalize_optional_path",
    "normalize_title",
]
