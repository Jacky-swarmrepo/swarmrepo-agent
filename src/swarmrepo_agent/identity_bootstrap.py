"""Shared reviewed identity bootstrap helpers for the public starter CLI."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from swarmrepo_sdk import AuthError, SwarmClient
from swarmrepo_agent_runtime.identity import load_token_store
from swarmrepo_agent_runtime.legal import prompt_for_required_acceptances
from swarmrepo_agent_runtime.state import (
    acquire_state_lock,
    agent_state_path,
    credentials_path,
    legal_state_path,
    migrate_legacy_token_store,
    resolve_state_dir,
    save_state_document,
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _credentials_payload(
    *,
    access_token: str,
    agent_name: str,
    provider: str,
    model: str,
    base_url: str | None,
    owner_id: Any,
    saved_at: str,
) -> dict[str, Any]:
    return {
        "access_token": access_token,
        "agent_name": agent_name,
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "owner_id": str(owner_id),
        "saved_at": saved_at,
    }


def _agent_state_payload(
    *,
    agent: Any,
    owner_id: Any | None = None,
    saved_at: str,
) -> dict[str, Any]:
    return {
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "provider": agent.provider,
        "model": agent.model,
        "base_url": agent.base_url,
        "merged_count": agent.merged_count,
        "created_at": agent.created_at.isoformat(),
        "owner_id": str(owner_id) if owner_id is not None else None,
        "saved_at": saved_at,
    }


def _legal_state_payload(
    *,
    requirements: Any,
    acceptances: list[Any],
    saved_at: str,
) -> dict[str, Any]:
    return {
        "requirements": [
            {
                "requirement_id": item.requirement_id,
                "kind": item.kind,
                "label": item.label,
                "version": item.version,
                "required": item.required,
            }
            for item in requirements.requirements
        ],
        "accepted_documents": [
            {
                "requirement_id": acceptance.requirement_id,
                "accepted": acceptance.accepted,
                "version": acceptance.version,
                "accepted_at": acceptance.accepted_at.isoformat(),
            }
            for acceptance in acceptances
        ],
        "saved_at": saved_at,
    }


def _save_runtime_state(
    *,
    state_dir: Path,
    agent: Any,
    owner_id: Any,
    access_token: str,
    provider: str,
    model: str,
    base_url: str | None,
    requirements: Any,
    acceptances: list[Any],
) -> None:
    saved_at = datetime.now(timezone.utc).isoformat()
    save_state_document(
        credentials_path(state_dir),
        _credentials_payload(
            access_token=access_token,
            agent_name=agent.name,
            provider=provider,
            model=model,
            base_url=base_url,
            owner_id=owner_id,
            saved_at=saved_at,
        ),
    )
    save_state_document(
        agent_state_path(state_dir),
        _agent_state_payload(agent=agent, owner_id=owner_id, saved_at=saved_at),
    )
    save_state_document(
        legal_state_path(state_dir),
        _legal_state_payload(
            requirements=requirements,
            acceptances=acceptances,
            saved_at=saved_at,
        ),
    )


async def ensure_identity(
    client: SwarmClient,
    *,
    state_dir: str | os.PathLike[str] | None = None,
) -> tuple[Any, Path]:
    """Resolve or bootstrap the current reviewed starter identity."""

    provider = _required_env("EXTERNAL_PROVIDER")
    api_key = _required_env("EXTERNAL_API_KEY")
    model = _required_env("EXTERNAL_MODEL")
    base_url = os.getenv("EXTERNAL_BASE_URL") or None
    agent_name = os.getenv("AGENT_NAME", f"custom-agent-{provider}")
    resolved_state_dir = resolve_state_dir(state_dir or os.getenv("AGENT_STATE_DIR"))

    client.set_byok_context(
        provider=provider,
        model=model,
        external_api_key=api_key,
        base_url_override=base_url,
    )

    with acquire_state_lock(resolved_state_dir):
        migrate_legacy_token_store(state_dir=resolved_state_dir)
        token_store = load_token_store(credentials_path(resolved_state_dir))
        token = token_store.get("access_token")
        if isinstance(token, str) and token.strip():
            client.set_access_token(token.strip())
            try:
                me = await client.get_me()
                save_state_document(
                    agent_state_path(resolved_state_dir),
                    _agent_state_payload(
                        agent=me,
                        owner_id=token_store.get("owner_id"),
                        saved_at=datetime.now(timezone.utc).isoformat(),
                    ),
                )
                return me, resolved_state_dir
            except AuthError:
                client.set_access_token(None)

        requirements = await client.get_registration_requirements()
        acceptances = prompt_for_required_acceptances(requirements)
        grant = await client.accept_for_registration(acceptances=acceptances)
        registration = await client.register_agent(
            agent_name=agent_name,
            external_api_key=api_key,
            provider=provider,
            model=model,
            base_url=base_url,
            registration_grant=grant.registration_grant,
        )
        if not registration.access_token:
            raise RuntimeError("Registration did not return an access token.")

        client.set_access_token(registration.access_token)
        _save_runtime_state(
            state_dir=resolved_state_dir,
            agent=registration.agent,
            owner_id=registration.owner_id,
            access_token=registration.access_token,
            provider=provider,
            model=model,
            base_url=base_url,
            requirements=requirements,
            acceptances=acceptances,
        )
        return registration.agent, resolved_state_dir
