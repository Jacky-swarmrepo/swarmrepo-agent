"""Summary builders for the reviewed public starter status commands."""

from __future__ import annotations

from datetime import datetime, timezone
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


def _required_requirement_ids(legal: Mapping[str, Any]) -> set[str]:
    requirements = legal.get("requirements")
    if isinstance(requirements, list):
        values = {
            str(item.get("requirement_id")).strip()
            for item in requirements
            if isinstance(item, Mapping)
            and item.get("required") is not False
            and str(item.get("requirement_id") or "").strip()
        }
        if values:
            return values
    if (
        legal.get("accepted_documents")
        or legal.get("tos_version")
        or legal.get("agent_contributor_terms_version")
        or legal.get("accepted_at")
    ):
        return {"platform-tos", "agent-contributor-terms"}
    return set()


def _accepted_requirement_ids(legal: Mapping[str, Any]) -> set[str]:
    accepted_documents = legal.get("accepted_documents")
    if not isinstance(accepted_documents, list):
        return set()
    return {
        str(item.get("requirement_id")).strip()
        for item in accepted_documents
        if isinstance(item, Mapping)
        and item.get("accepted") is not False
        and str(item.get("requirement_id") or "").strip()
    }


def build_auth_summary(credentials: Mapping[str, Any]) -> dict[str, Any]:
    """Build a minimal auth summary from structured starter credentials."""
    refresh_token_present = bool(credentials.get("refresh_token"))
    access_token_expires_at = _normalize_timestamp(credentials.get("access_token_expires_at"))
    refresh_token_expires_at = _normalize_timestamp(credentials.get("refresh_token_expires_at"))
    return {
        "access_token_present": bool(credentials.get("access_token")),
        "refresh_token_present": refresh_token_present,
        "access_token_saved_at": credentials.get("saved_at"),
        "last_refresh_at": credentials.get("last_refresh_at"),
        "access_token_expires_at": access_token_expires_at,
        "refresh_token_expires_at": refresh_token_expires_at,
        "access_token_expired": _timestamp_is_expired(access_token_expires_at),
        "refresh_token_expired": _timestamp_is_expired(refresh_token_expires_at),
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
    required_requirement_ids = _required_requirement_ids(legal)
    accepted_requirement_ids = _accepted_requirement_ids(legal)
    registration_grant_expires_at = _normalize_timestamp(legal.get("registration_grant_expires_at"))
    registration_grant_present = bool(legal.get("registration_grant"))
    registration_grant_consumed_raw = legal.get("registration_grant_consumed")
    registration_grant_consumed = (
        bool(registration_grant_consumed_raw)
        if registration_grant_consumed_raw is not None
        else False
    )
    required_acceptance_complete = bool(remote_binding) or (
        bool(required_requirement_ids)
        and all(
            requirement_id in accepted_requirement_ids
            for requirement_id in required_requirement_ids
        )
    )

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
            or remote_binding.get("accepted_by_principal_type")
            or legal.get("accepted_by_principal_type")
            or remote_binding.get("accepted_by_actor_type")
            or legal.get("accepted_by_actor_type")
        ),
        "accepted_by_principal_id": (
            remote_evidence.get("principal_id")
            or remote_binding.get("accepted_by_principal_id")
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
        "requirements_available": bool(required_requirement_ids) or bool(remote_binding),
        "required_acceptance_complete": required_acceptance_complete,
        "required_requirement_ids": sorted(required_requirement_ids),
        "accepted_requirement_ids": sorted(accepted_requirement_ids),
        "registration_grant_present": registration_grant_present,
        "registration_grant_expires_at": registration_grant_expires_at,
        "registration_grant_expired": (
            _timestamp_is_expired(registration_grant_expires_at)
            if registration_grant_present
            else None
        ),
        "registration_grant_consumed": registration_grant_consumed,
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
        "merged_count": agent.get("merged_count"),
        "created_at": agent.get("created_at"),
    }


def build_endpoint_summary(*, base_url: str, state_dir: str) -> dict[str, Any]:
    """Build the starter endpoint summary."""
    return {
        "base_url": base_url,
        "state_dir": state_dir,
    }


def _next_step(command: str, reason: str) -> dict[str, str]:
    return {
        "command": command,
        "reason": reason,
    }


def _normalize_timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        normalized = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    else:
        normalized = normalized.astimezone(timezone.utc)
    return normalized.isoformat()


def _timestamp_is_expired(value: str | None) -> bool | None:
    if value is None:
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)
    return timestamp <= datetime.now(timezone.utc)


def build_state_checks(
    *,
    auth_summary: Mapping[str, Any],
    legal_summary: Mapping[str, Any],
    agent_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Build stable readiness checks for the reviewed starter state."""
    access_token_ready = bool(auth_summary.get("access_token_present")) and (
        auth_summary.get("access_token_expired") is not True
    )
    refresh_token_ready = bool(auth_summary.get("refresh_token_present")) and (
        auth_summary.get("refresh_token_expired") is not True
    )
    registration_grant_ready = bool(legal_summary.get("registration_grant_present")) and (
        legal_summary.get("registration_grant_expired") is not True
    ) and not bool(legal_summary.get("registration_grant_consumed"))
    return {
        "access_token_ready": access_token_ready,
        "refresh_token_ready": refresh_token_ready,
        "legal_requirements_ready": bool(legal_summary.get("requirements_available")),
        "legal_ready": bool(legal_summary.get("required_acceptance_complete")),
        "registration_grant_ready": registration_grant_ready,
        "agent_ready": bool(agent_summary.get("agent_id") or agent_summary.get("agent_name")),
        "remote_legal_validated": legal_summary.get("summary_source") == "remote_validated",
        "legal_evidence_complete": legal_summary.get("evidence_complete"),
    }


def build_workflow_navigation(*, state_checks: Mapping[str, Any]) -> dict[str, Any]:
    """Build stable next-step hints for the reviewed public status surface."""
    is_ready = all(
        (
            state_checks.get("access_token_ready"),
            state_checks.get("legal_ready"),
            state_checks.get("agent_ready"),
        )
    )
    if not is_ready:
        if state_checks.get("refresh_token_ready") and state_checks.get("legal_ready") and state_checks.get("agent_ready"):
            return {
                "workflow_phase": "needs_token_refresh",
                "next_step_commands": [
                    _next_step(
                        "swarmrepo-agent agent refresh --json",
                        "Rotate reviewed local credentials from the stored refresh token.",
                    ),
                    _next_step(
                        "swarmrepo-agent status auth --json",
                        "Inspect local credential expiry and refresh-token availability.",
                    ),
                    _next_step(
                        "swarmrepo-agent auth whoami --json",
                        "Validate the refreshed access token against the hosted identity surface.",
                    ),
                ],
            }
        if not state_checks.get("legal_requirements_ready"):
            return {
                "workflow_phase": "needs_legal_requirements",
                "next_step_commands": [
                    _next_step(
                        "swarmrepo-agent legal requirements --json",
                        "Fetch the active reviewed legal requirements and store the registration context.",
                    ),
                    _next_step(
                        "swarmrepo-agent legal accept --yes --json",
                        "Accept the reviewed legal summaries and store one registration grant.",
                    ),
                    _next_step(
                        "swarmrepo-agent agent onboard --yes --json",
                        "Use the one-shot onboarding flow instead of the explicit legal steps.",
                    ),
                ],
            }
        if not state_checks.get("legal_ready"):
            return {
                "workflow_phase": "needs_legal_acceptance",
                "next_step_commands": [
                    _next_step(
                        "swarmrepo-agent legal accept --yes --json",
                        "Accept the active reviewed legal summaries and store one registration grant.",
                    ),
                    _next_step(
                        "swarmrepo-agent status legal --json",
                        "Inspect the saved legal requirement snapshot before accepting.",
                    ),
                    _next_step(
                        "swarmrepo-agent agent onboard --yes --json",
                        "Use the one-shot onboarding flow instead of the explicit legal steps.",
                    ),
                ],
            }
        if state_checks.get("registration_grant_ready") and not state_checks.get("agent_ready"):
            return {
                "workflow_phase": "ready_for_registration",
                "next_step_commands": [
                    _next_step(
                        "swarmrepo-agent agent register --agent-name <agent-name> --json",
                        "Consume the stored reviewed registration grant and create the starter identity.",
                    ),
                    _next_step(
                        "swarmrepo-agent status legal --json",
                        "Inspect the stored registration grant and reviewed legal summary.",
                    ),
                    _next_step(
                        "swarmrepo-agent status auth --json",
                        "Confirm whether this state directory is still missing credentials before registration.",
                    ),
                ],
            }
        return {
            "workflow_phase": "needs_onboarding",
            "next_step_commands": [
                _next_step(
                    "swarmrepo-agent agent onboard --yes --json",
                    "Run the reviewed idempotent onboarding flow for this machine.",
                ),
                _next_step(
                    "swarmrepo-agent status auth --json",
                    "Confirm whether a local access token is already present.",
                ),
                _next_step(
                    "swarmrepo-agent status agent --json",
                    "Inspect whether a starter-local agent identity already exists.",
                ),
                _next_step(
                    "swarmrepo-agent status legal --json",
                    "Inspect the currently saved legal acceptance summary.",
                ),
            ],
        }

    return {
        "workflow_phase": "ready_for_ai_workflows",
        "next_step_commands": [
            _next_step(
                "swarmrepo-agent auth whoami --json",
                "Confirm the current remote-validated identity and legal context.",
            ),
            _next_step(
                "swarmrepo-agent repo create --name demo-repo --language python",
                "Create one reviewed repository container for a new workflow.",
            ),
            _next_step(
                "swarmrepo-agent repo import --local-path ./project-src",
                "Import one existing local source tree into a new reviewed repository.",
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


def build_overview(
    *,
    auth_summary: Mapping[str, Any],
    legal_summary: Mapping[str, Any],
    agent_summary: Mapping[str, Any],
    endpoint_summary: Mapping[str, Any],
    state_checks: Mapping[str, Any],
    workflow_navigation: Mapping[str, Any],
    current_agent_legal_evidence_summary: Mapping[str, Any] | None,
    remote_legal_error: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the combined status payload."""
    return {
        "auth_summary": dict(auth_summary),
        "legal_summary": dict(legal_summary),
        "agent_summary": dict(agent_summary),
        "endpoint_summary": dict(endpoint_summary),
        "state_checks": dict(state_checks),
        "workflow_navigation": dict(workflow_navigation),
        "current_agent_legal_evidence_summary": (
            dict(current_agent_legal_evidence_summary)
            if current_agent_legal_evidence_summary
            else None
        ),
        "remote_legal_error": dict(remote_legal_error) if remote_legal_error else None,
    }


__all__ = [
    "build_agent_summary",
    "build_auth_summary",
    "build_endpoint_summary",
    "build_legal_summary",
    "build_overview",
    "build_state_checks",
    "build_workflow_navigation",
]
