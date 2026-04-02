"""Reviewed legal-state persistence helpers for the public starter CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from swarmrepo_agent_runtime.legal import render_legal_acceptance_prompt
from swarmrepo_agent_runtime.legal_terms import (
    CONTRIBUTOR_TERMS_REQUIREMENT_ID,
    FULL_CONTRIBUTOR_TERMS_TEXT,
)
from swarmrepo_agent_runtime.state import legal_state_path, save_state_document

from .legal_context import ReviewedLegalContext


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    text = str(value).strip()
    return text or None


def _serialize_accepted_documents(acceptances: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "requirement_id": acceptance.requirement_id,
            "accepted": acceptance.accepted,
            "version": acceptance.version,
            "accepted_at": _serialize_datetime(acceptance.accepted_at),
        }
        for acceptance in acceptances
    ]


def _serialize_requirements(requirements: Any) -> list[dict[str, Any]]:
    return [
        {
            "requirement_id": item.requirement_id,
            "kind": item.kind,
            "label": item.label,
            "version": item.version,
            "required": item.required,
            "display_text": getattr(item, "display_text", None),
            "content_url": getattr(item, "content_url", None),
            "local_full_text": (
                FULL_CONTRIBUTOR_TERMS_TEXT
                if item.requirement_id == CONTRIBUTOR_TERMS_REQUIREMENT_ID
                else None
            ),
        }
        for item in requirements.requirements
    ]


def _requirement_version(requirements: Any, requirement_ids: tuple[str, ...]) -> str | None:
    for item in requirements.requirements:
        requirement_id = getattr(item, "requirement_id", None)
        if isinstance(requirement_id, str) and requirement_id in requirement_ids:
            version = getattr(item, "version", None)
            if isinstance(version, str) and version.strip():
                return version.strip()
    return None


def _serialize_legal_binding_summary(legal_binding_summary: Any) -> dict[str, Any]:
    if legal_binding_summary is None:
        return {}
    if hasattr(legal_binding_summary, "model_dump"):
        payload = legal_binding_summary.model_dump(mode="json")
    else:
        payload = dict(legal_binding_summary)
    return {
        key: value
        for key, value in payload.items()
        if value is not None
    }


def build_reviewed_legal_state(
    existing_legal: Mapping[str, Any] | None,
    *,
    legal_context: ReviewedLegalContext,
    requirements: Any | None = None,
    acceptances: Sequence[Any] | None = None,
    registration_grant: Any | None = None,
    registration_grant_consumed: bool | None = None,
    legal_binding_summary: Any | None = None,
    saved_at: str | None = None,
) -> dict[str, Any]:
    """Build the merged reviewed legal-state document."""
    payload = dict(existing_legal or {})
    payload["registration_context"] = legal_context.registration_context_payload()
    payload["client_context"] = legal_context.client_context_payload()
    payload["saved_at"] = saved_at or datetime.now(timezone.utc).isoformat()

    if requirements is not None:
        payload["requirements"] = _serialize_requirements(requirements)
        payload["rendered_prompt_text"] = render_legal_acceptance_prompt(requirements)
        payload["registration_grant_required"] = bool(
            getattr(requirements, "registration_grant_required", True)
        )
        payload["notes"] = list(getattr(requirements, "notes", []) or [])
        tos_version = _requirement_version(requirements, ("platform-tos", "platform_tos"))
        if tos_version is not None:
            payload["tos_version"] = tos_version
        agent_terms_version = _requirement_version(
            requirements,
            ("agent-contributor-terms", "agent_contributor_terms"),
        )
        if agent_terms_version is not None:
            payload["agent_contributor_terms_version"] = agent_terms_version

    if acceptances is not None:
        accepted_documents = _serialize_accepted_documents(acceptances)
        payload["accepted_documents"] = accepted_documents
        first_accepted_at = next(
            (
                item.get("accepted_at")
                for item in accepted_documents
                if isinstance(item.get("accepted_at"), str)
            ),
            None,
        )
        if first_accepted_at is not None:
            payload["accepted_at"] = first_accepted_at

    if registration_grant is not None:
        payload["registration_grant"] = registration_grant.registration_grant
        payload["registration_grant_issued_at"] = _serialize_datetime(registration_grant.issued_at)
        payload["registration_grant_expires_at"] = _serialize_datetime(
            getattr(registration_grant, "expires_at", None)
        )
        payload["registration_grant_consumed"] = False
    elif registration_grant_consumed is True:
        payload.pop("registration_grant", None)
        payload["registration_grant_consumed"] = True

    binding_payload = _serialize_legal_binding_summary(legal_binding_summary)
    if binding_payload:
        payload["legal_binding_summary"] = binding_payload
        payload.update(binding_payload)

    return payload


def save_reviewed_legal_state(
    state_dir: str,
    payload: Mapping[str, Any],
) -> None:
    """Persist the reviewed legal-state snapshot."""
    save_state_document(legal_state_path(state_dir), dict(payload))


__all__ = ["build_reviewed_legal_state", "save_reviewed_legal_state"]
