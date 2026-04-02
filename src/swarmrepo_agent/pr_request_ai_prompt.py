"""Prompt-backed helpers for reviewed public `pr request-ai`."""

from __future__ import annotations

import argparse
from typing import Any, Mapping

from swarmrepo_sdk import SwarmClient

from .file_inputs import load_optional_text_file
from .pr_request_ai_common import (
    ISSUE_REFERENCE_WARNING,
    build_prompt_request_description,
    build_prompt_result,
    normalize_optional_path,
    normalize_title,
)


async def dispatch_prompt_request(
    args: argparse.Namespace,
    *,
    client: SwarmClient,
    repo_id: str,
    current_agent_legal_evidence_summary: Mapping[str, Any] | None,
    current_agent_legal_error: Mapping[str, str] | None,
    legal_state_warnings: list[str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Create one prompt-backed durable delegation issue."""

    warnings = [ISSUE_REFERENCE_WARNING, *legal_state_warnings]
    context_text = load_optional_text_file(args.context_file, label="context")
    diff_text = load_optional_text_file(args.diff_file, label="diff")
    issue_title = normalize_title(args.prompt)
    issue_description = build_prompt_request_description(
        args,
        context_text=context_text,
        diff_text=diff_text,
        warnings=warnings,
    )
    issue = await client.create_issue(
        repo_id,
        title=issue_title,
        description=issue_description,
    )
    normalized_request = {
        "repo_id": repo_id,
        "prompt": args.prompt,
        "title": issue_title,
        "base_branch": args.base_branch,
        "changed_files_only": bool(args.changed_files_only),
        "context_file": normalize_optional_path(args.context_file),
        "diff_file": normalize_optional_path(args.diff_file),
    }
    data, text_lines = build_prompt_result(
        repo_id=repo_id,
        issue=issue.model_dump(mode="json"),
        normalized_request=normalized_request,
        current_agent_legal_evidence_summary=current_agent_legal_evidence_summary,
        current_agent_legal_error=current_agent_legal_error,
    )
    return data, warnings, text_lines


__all__ = ["dispatch_prompt_request"]
