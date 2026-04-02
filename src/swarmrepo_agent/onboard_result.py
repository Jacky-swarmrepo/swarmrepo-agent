"""Result builders for the reviewed public `agent onboard` command."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .legal_evidence import build_current_agent_legal_evidence_summary
from .status_summary import (
    build_agent_summary,
    build_auth_summary,
    build_endpoint_summary,
    build_legal_summary,
)


def _next_step(command: str, reason: str) -> dict[str, str]:
    return {
        "command": command,
        "reason": reason,
    }


def build_workflow_navigation() -> dict[str, Any]:
    """Build stable follow-up hints for the reviewed public onboarding flow."""
    return {
        "workflow_phase": "ready_for_ai_workflows",
        "next_step_commands": [
            _next_step(
                "swarmrepo-agent auth whoami --json",
                "Confirm the current remote-validated identity and legal context.",
            ),
            _next_step(
                "swarmrepo-agent repo create --name demo-repo --language python",
                "Create the first reviewed repository container for this starter identity.",
            ),
            _next_step(
                'swarmrepo-agent pr request-ai --repo-id <repo-id> --prompt "Fix the parser crash."',
                "Delegate one reviewed AI change request after a repository exists.",
            ),
            _next_step(
                "swarmrepo-agent status legal --json",
                "Inspect the authenticated remote legal evidence summary when needed.",
            ),
        ],
    }


def build_onboarding_payload(
    *,
    onboarding_state: str,
    state_dir: str,
    base_url: str,
    credentials: Mapping[str, Any],
    legal: Mapping[str, Any],
    agent: Mapping[str, Any],
    steps_executed: list[str],
    remote_legal_state: Mapping[str, Any] | None,
    remote_legal_error: Mapping[str, str] | None,
    warnings: list[str],
) -> dict[str, Any]:
    """Build the stable public payload for `agent onboard`."""
    auth_summary = build_auth_summary(credentials)
    legal_summary = build_legal_summary(legal, remote_legal_state=remote_legal_state)
    agent_summary = build_agent_summary(agent)
    endpoint_summary = build_endpoint_summary(
        base_url=base_url,
        state_dir=state_dir,
    )
    workflow_navigation = build_workflow_navigation()
    return {
        "command": "agent onboard",
        "state_dir": state_dir,
        "data": {
            "onboarding_state": onboarding_state,
            "steps_executed": steps_executed,
            "auth_summary": auth_summary,
            "legal_summary": legal_summary,
            "agent_summary": agent_summary,
            "endpoint_summary": endpoint_summary,
            "workflow_navigation": workflow_navigation,
            "current_agent_legal_evidence_summary": build_current_agent_legal_evidence_summary(
                remote_legal_state
            ),
            "remote_legal_error": dict(remote_legal_error) if remote_legal_error else None,
        },
        "warnings": warnings,
    }


def render_onboarding_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    """Render the reviewed public onboarding payload as JSON or concise text."""
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    data = payload.get("data") or {}
    legal_summary = data.get("legal_summary") or {}
    agent_summary = data.get("agent_summary") or {}
    workflow_navigation = data.get("workflow_navigation") or {}
    state_dir = payload.get("state_dir") or "(unknown)"

    onboarding_state = data.get("onboarding_state") or "(unknown)"
    state_labels = {
        "already_ready": "already ready",
        "registered_ready": "registered ready",
    }
    evidence_complete = legal_summary.get("evidence_complete")
    if evidence_complete is True:
        evidence_label = "complete"
    elif evidence_complete is False:
        evidence_label = "partial"
    else:
        evidence_label = "(local only)"

    print("SwarmRepo onboarding:")
    print(f"- state: {state_labels.get(onboarding_state, onboarding_state)}")
    print(f"- workflow phase: {workflow_navigation.get('workflow_phase') or '(unknown)'}")
    print(f"- agent: {agent_summary.get('agent_name') or '(missing)'}")
    print(
        "- legal: "
        f"{legal_summary.get('tos_version') or '(missing)'} / "
        f"{legal_summary.get('agent_contributor_terms_version') or '(missing)'}"
    )
    print(f"- legal evidence: {evidence_label}")
    print(f"- state dir: {state_dir}")

    for hint in workflow_navigation.get("next_step_commands") or []:
        command = hint.get("command")
        if command:
            print(f"Next: {command}")

    for warning in payload.get("warnings") or []:
        print(f"warning: {warning}")


__all__ = [
    "build_onboarding_payload",
    "build_workflow_navigation",
    "render_onboarding_payload",
]
