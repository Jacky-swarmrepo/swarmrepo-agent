"""Reviewed legal-context helpers for the public starter CLI."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping
import uuid


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True, slots=True)
class ReviewedLegalContext:
    """Normalized reviewed legal context for explicit starter commands."""

    actor_type: str
    actor_id: str
    org_id: str | None
    acting_user_id: str
    principal_type: str
    principal_id: str
    client_kind: str
    client_version: str
    platform: str | None
    hostname_hint: str | None
    device_id: str | None

    def client_kwargs(self) -> dict[str, str]:
        """Return keyword arguments for the reviewed public SDK client."""
        payload = {
            "legal_actor_type": self.actor_type,
            "legal_actor_id": self.actor_id,
            "legal_org_id": self.org_id,
            "legal_acting_user_id": self.acting_user_id,
            "legal_client_kind": self.client_kind,
            "legal_client_version": self.client_version,
            "legal_platform": self.platform,
            "legal_hostname_hint": self.hostname_hint,
            "legal_device_id": self.device_id,
        }
        return {
            key: value
            for key, value in payload.items()
            if isinstance(value, str) and value.strip()
        }

    def registration_context_payload(self) -> dict[str, str | None]:
        """Return the stable reviewed registration-context snapshot."""
        return {
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "org_id": self.org_id,
            "acting_user_id": self.acting_user_id,
            "principal_type": self.principal_type,
            "principal_id": self.principal_id,
        }

    def client_context_payload(self) -> dict[str, str | None]:
        """Return the stable reviewed client-context snapshot."""
        return {
            "client_kind": self.client_kind,
            "client_version": self.client_version,
            "platform": self.platform,
            "hostname_hint": self.hostname_hint,
            "device_id": self.device_id,
        }


def resolve_reviewed_legal_context(
    *,
    legal_state: Mapping[str, Any] | None,
    default_client_kind: str,
    default_client_version: str,
) -> ReviewedLegalContext:
    """Resolve the reviewed legal context from env, local state, and defaults."""
    legal_state = legal_state or {}
    registration_context = _mapping(legal_state.get("registration_context"))
    client_context = _mapping(legal_state.get("client_context"))

    actor_type = (
        os.getenv("SWARM_LEGAL_ACTOR_TYPE")
        or registration_context.get("actor_type")
        or "individual_account"
    )
    normalized_actor_type = str(actor_type).strip().lower() or "individual_account"

    actor_id = _optional_string(
        os.getenv("SWARM_LEGAL_ACTOR_ID")
        or registration_context.get("actor_id")
        or uuid.uuid4()
    )
    assert actor_id is not None

    org_id = _optional_string(
        os.getenv("SWARM_LEGAL_ORG_ID") or registration_context.get("org_id")
    )
    if org_id is None and normalized_actor_type == "organization_account":
        org_id = actor_id

    acting_user_id = _optional_string(
        os.getenv("SWARM_LEGAL_ACTING_USER_ID")
        or registration_context.get("acting_user_id")
        or actor_id
    )
    assert acting_user_id is not None

    client_kind = _optional_string(
        os.getenv("SWARM_LEGAL_CLIENT_KIND")
        or client_context.get("client_kind")
        or default_client_kind
    )
    assert client_kind is not None
    client_version = _optional_string(
        os.getenv("SWARM_LEGAL_CLIENT_VERSION")
        or client_context.get("client_version")
        or default_client_version
    )
    assert client_version is not None

    platform = _optional_string(
        os.getenv("SWARM_LEGAL_PLATFORM") or client_context.get("platform")
    )
    hostname_hint = _optional_string(
        os.getenv("SWARM_LEGAL_HOSTNAME_HINT") or client_context.get("hostname_hint")
    )
    device_id = _optional_string(
        os.getenv("SWARM_LEGAL_DEVICE_ID") or client_context.get("device_id")
    )

    principal_type = normalized_actor_type
    principal_id = org_id if normalized_actor_type == "organization_account" and org_id else actor_id

    return ReviewedLegalContext(
        actor_type=normalized_actor_type,
        actor_id=actor_id,
        org_id=org_id,
        acting_user_id=acting_user_id,
        principal_type=principal_type,
        principal_id=principal_id,
        client_kind=client_kind,
        client_version=client_version,
        platform=platform,
        hostname_hint=hostname_hint,
        device_id=device_id,
    )


__all__ = ["ReviewedLegalContext", "resolve_reviewed_legal_context"]
