"""Shared legal-evidence helpers for reviewed public starter commands."""

from __future__ import annotations

from typing import Any, Mapping


def build_current_agent_legal_evidence_summary(
    legal_state: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Build the stable legal-evidence summary used by companion commands."""
    if legal_state is None:
        return None
    binding = legal_state.get("legal_binding_summary")
    evidence = legal_state.get("legal_evidence_summary")
    binding = binding if isinstance(binding, Mapping) else {}
    evidence = evidence if isinstance(evidence, Mapping) else {}
    if not binding and not evidence:
        return None
    return {
        "principal_type": evidence.get("principal_type") or binding.get("accepted_by_principal_type"),
        "principal_id": evidence.get("principal_id") or binding.get("accepted_by_principal_id"),
        "tos_version": binding.get("tos_version"),
        "agent_contributor_terms_version": binding.get("agent_contributor_terms_version"),
        "accepted_at": binding.get("accepted_at"),
        "evidence_complete": evidence.get("evidence_complete"),
        "platform_tos": evidence.get("platform_tos"),
        "agent_contributor_terms": evidence.get("agent_contributor_terms"),
        "summary_source": "remote_validated",
    }


def build_legal_state_follow_up_lines() -> list[str]:
    """Return stable follow-up hints for legal-state companion reads."""
    return [
        "See also: swarmrepo-agent status legal --json",
    ]


__all__ = [
    "build_current_agent_legal_evidence_summary",
    "build_legal_state_follow_up_lines",
]
