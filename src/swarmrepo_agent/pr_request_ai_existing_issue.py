"""Existing-issue helpers for reviewed public `pr request-ai`."""

from __future__ import annotations

import argparse
from typing import Any, Mapping

from swarmrepo_sdk import SwarmClient

from .file_inputs import load_optional_text_file
from .pr_request_ai_common import (
    ISSUE_REFERENCE_WARNING,
    LINKED_ISSUE_WARNING,
    build_existing_issue_result,
    build_linked_issue_request_description,
    build_linked_issue_request_title,
    build_linked_issue_result,
    has_existing_issue_supplemental_inputs,
    normalize_optional_path,
)


async def _load_existing_issue(
    *,
    client: SwarmClient,
    repo_id: str,
    issue_id: str,
) -> Any:
    issue = await client.get_repo_issue(repo_id, issue_id)
    if issue is None:
        raise RuntimeError("Existing issue could not be found for this repository.")
    if issue.status != "open":
        raise RuntimeError("Only open issues can be used as AI delegation requests.")
    return issue


async def dispatch_existing_issue_request(
    args: argparse.Namespace,
    *,
    client: SwarmClient,
    repo_id: str,
    current_agent_legal_evidence_summary: Mapping[str, Any] | None,
    current_agent_legal_error: Mapping[str, str] | None,
    legal_state_warnings: list[str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Reuse one existing open issue or create a linked delegation issue."""

    issue = await _load_existing_issue(
        client=client,
        repo_id=repo_id,
        issue_id=str(args.issue_id),
    )
    if not has_existing_issue_supplemental_inputs(args):
        warnings = [ISSUE_REFERENCE_WARNING, *legal_state_warnings]
        data, text_lines = build_existing_issue_result(
            repo_id=repo_id,
            issue=issue.model_dump(mode="json"),
            current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
            current_agent_legal_error=current_agent_legal_error,
        )
        return data, warnings, text_lines

    warnings = [ISSUE_REFERENCE_WARNING, LINKED_ISSUE_WARNING, *legal_state_warnings]
    context_text = load_optional_text_file(args.context_file, label="context")
    diff_text = load_optional_text_file(args.diff_file, label="diff")
    delegation_issue = await client.create_issue(
        repo_id,
        title=build_linked_issue_request_title(issue.model_dump(mode="json")),
        description=build_linked_issue_request_description(
            args,
            source_issue=issue.model_dump(mode="json"),
            context_text=context_text,
            diff_text=diff_text,
            warnings=warnings,
        ),
    )
    normalized_request = {
        "repo_id": repo_id,
        "source_issue_id": str(issue.id),
        "delegation_issue_id": str(delegation_issue.id),
        "base_branch": args.base_branch,
        "changed_files_only": bool(args.changed_files_only),
        "context_file": normalize_optional_path(args.context_file),
        "diff_file": normalize_optional_path(args.diff_file),
    }
    data, text_lines = build_linked_issue_result(
        repo_id=repo_id,
        source_issue=issue.model_dump(mode="json"),
        issue=delegation_issue.model_dump(mode="json"),
        normalized_request=normalized_request,
        current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
        current_agent_legal_error=current_agent_legal_error,
    )
    return data, warnings, text_lines


__all__ = ["dispatch_existing_issue_request"]
