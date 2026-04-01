"""Summary builders for the reviewed public starter status commands."""

from __future__ import annotations

from typing import Any, Mapping


_PLATFORM_TOS_REQUIREMENT_IDS = ("platform-tos", "platform_tos")
_AGENT_TERMS_REQUIREMENT_IDS = (
    "agent-contributor-terms",
    "agent_contributor_terms",
)


def _pick_accepted_document(
    legal: Mapping[str, Any],
    requirement_ids: tuple[str, ...],
) -> Mapping[str, Any]:
    accepted_documents = legal.get("accepted_documents")
    if not isinstance(accepted_documents, list):
        return {}
    for item in accepted_documents:
        if not isinstance(item, Mapping):
            continue
        requirement_id = item.get("requirement_id")
        if isinstance(requirement_id, str) and requirement_id in requirement_ids:
            return item
    return {}


def build_auth_summary(credentials: Mapping[str, Any]) -> dict[str, Any]:
    """Build a minimal auth summary from structured starter credentials."""
    refresh_token_present = bool(credentials.get("refresh_token"))
    return {
        "access_token_present": bool(credentials.get("access_token")),
        "refresh_token_present": refresh_token_present,
        "access_token_saved_at": credentials.get("saved_at"),
        "refresh_token_storage": "local_state" if refresh_token_present else None,
    }


def build_legal_summary(
    legal: Mapping[str, Any],
    *,
    remote_legal_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a reviewed legal summary from local and optional remote state."""
    local_platform_tos = _pick_accepted_document(legal, _PLATFORM_TOS_REQUIREMENT_IDS)
    local_agent_terms = _pick_accepted_document(legal, _AGENT_TERMS_REQUIREMENT_IDS)

    remote_binding = (
        remote_legal_state.get("legal_binding_summary")
        if remote_legal_state is not None
        else None
    ) or {}
    remote_evidence = (
        remote_legal_state.get("legal_evidence_summary")
        if remote_legal_state is not None
        else None
    ) or {}

    summary_source = "remote_validated" if remote_binding else "local_state"
    return {
        "tos_version": (
            remote_binding.get("tos_version")
            or local_platform_tos.get("version")
            or legal.get("tos_version")
        ),
        "agent_contributor_terms_version": (
            remote_binding.get("agent_contributor_terms_version")
            or local_agent_terms.get("version")
            or legal.get("agent_contributor_terms_version")
        ),
        "accepted_by_actor_type": (
            remote_binding.get("accepted_by_actor_type")
            or legal.get("accepted_by_actor_type")
        ),
        "accepted_by_actor_id": (
            remote_binding.get("accepted_by_actor_id")
            or legal.get("accepted_by_actor_id")
        ),
        "accepted_by_org_id": (
            remote_binding.get("accepted_by_org_id")
            or legal.get("accepted_by_org_id")
        ),
        "accepted_by_principal_type": (
            remote_evidence.get("principal_type")
            or legal.get("accepted_by_principal_type")
            or remote_binding.get("accepted_by_actor_type")
            or legal.get("accepted_by_actor_type")
        ),
        "accepted_by_principal_id": (
            remote_evidence.get("principal_id")
            or legal.get("accepted_by_principal_id")
            or remote_binding.get("accepted_by_actor_id")
            or legal.get("accepted_by_actor_id")
        ),
        "accepted_at": (
            remote_binding.get("accepted_at")
            or local_platform_tos.get("accepted_at")
            or local_agent_terms.get("accepted_at")
            or legal.get("accepted_at")
        ),
        "summary_source": summary_source,
        "evidence_complete": (
            remote_evidence.get("evidence_complete")
            if remote_evidence
            else None
        ),
        "legal_evidence_summary": remote_evidence or None,
    }


def build_agent_summary(agent: Mapping[str, Any]) -> dict[str, Any]:
    """Build a minimal starter-local agent summary."""
    return {
        "agent_id": agent.get("agent_id"),
        "agent_name": agent.get("agent_name"),
        "provider": agent.get("provider"),
        "model": agent.get("model"),
        "base_url": agent.get("base_url"),
        "owner_id": agent.get("owner_id"),
    }


def build_endpoint_summary(*, base_url: str, state_dir: str) -> dict[str, Any]:
    """Build the starter endpoint summary."""
    return {
        "base_url": base_url,
        "state_dir": state_dir,
    }


def build_overview(
    *,
    auth_summary: Mapping[str, Any],
    legal_summary: Mapping[str, Any],
    agent_summary: Mapping[str, Any],
    endpoint_summary: Mapping[str, Any],
    remote_legal_error: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the combined status payload."""
    return {
        "auth_summary": dict(auth_summary),
        "legal_summary": dict(legal_summary),
        "agent_summary": dict(agent_summary),
        "endpoint_summary": dict(endpoint_summary),
        "remote_legal_error": dict(remote_legal_error) if remote_legal_error else None,
    }


__all__ = [
    "build_agent_summary",
    "build_auth_summary",
    "build_endpoint_summary",
    "build_legal_summary",
    "build_overview",
]
