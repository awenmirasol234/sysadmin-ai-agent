"""Unit tests for action security, allowlist validation, and approval token lifecycle."""

import pytest
from backend.config import settings
from backend.db import init_db
from backend.tools.actions import (
    SecurityError,
    compute_action_hash,
    create_approval_request,
    decide_approval,
    execute_approved_action,
    validate_target,
)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()
    orig_allowed = settings.ALLOWED_CONTAINERS
    settings.ALLOWED_CONTAINERS = ["*"]
    yield
    settings.ALLOWED_CONTAINERS = orig_allowed


def test_validate_target_allowed():
    # Wildcard allowlist permits valid arbitrary containers
    settings.ALLOWED_CONTAINERS = ["*"]
    validate_target("restart_container", "production-api")
    validate_target("start_container", "redis-cache")
    validate_target("stop_container", "worker-service")

    # Explicit allowlist
    settings.ALLOWED_CONTAINERS = ["app-frontend", "app-backend"]
    validate_target("restart_container", "app-frontend")
    validate_target("start_container", "app-backend")

    # Allowed services
    validate_target("restart_service", "docker")
    validate_target("restart_service", "ssh")


def test_validate_target_forbidden():
    # 1. Protected SysAdmin containers are ALWAYS blocked even in wildcard mode
    settings.ALLOWED_CONTAINERS = ["*"]
    with pytest.raises(SecurityError) as exc_info:
        validate_target("restart_container", "sysadmin-backend")
    assert "protected SysAdmin system component" in str(exc_info.value)

    with pytest.raises(SecurityError) as exc_info:
        validate_target("stop_container", "sysadmin-dashboard")
    assert "protected SysAdmin system component" in str(exc_info.value)

    # 2. Unauthorized container with explicit allowlist
    settings.ALLOWED_CONTAINERS = ["app-frontend"]
    with pytest.raises(SecurityError) as exc_info:
        validate_target("restart_container", "unauthorized-prod-db")
    assert "NOT in the allowed containers allowlist" in str(exc_info.value)

    # 3. Shell injection / illegal character attempt
    with pytest.raises(SecurityError):
        validate_target("restart_container", "app-frontend; rm -rf /")

    # 4. Unsupported action
    with pytest.raises(SecurityError) as exc_info:
        validate_target("delete_database", "app-frontend")
    assert "Unsupported action type" in str(exc_info.value)


def test_compute_action_hash():
    h1 = compute_action_hash("restart_container", "nginx")
    h2 = compute_action_hash("restart_container", "nginx")
    h3 = compute_action_hash("restart_container", "redis")

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # SHA-256 length


def test_approval_lifecycle():
    # 1. Create approval request
    req = create_approval_request(
        action_type="restart_container",
        target="nginx",
        reason="Nginx container is stopped.",
    )
    approval_id = req["approval_id"]
    assert req["status"] == "pending"

    # 2. Reject decision
    dec = decide_approval(approval_id, "reject")
    assert dec["status"] == "rejected"

    # 3. Cannot execute rejected approval
    res = execute_approved_action(approval_id)
    assert "Cannot execute" in res["error"]


def test_approval_replay_protection():
    # 1. Create and approve request
    req = create_approval_request(
        action_type="restart_container",
        target="nginx",
        reason="Nginx container is stopped.",
    )
    approval_id = req["approval_id"]
    decide_approval(approval_id, "approve")

    # 2. Execute (Mocked/Simulated or Docker call)
    res = execute_approved_action(approval_id)
    assert "result" in res or "error" in res

    # 3. Re-execution attempt MUST be blocked
    re_exec = execute_approved_action(approval_id)
    assert "Security violation" in re_exec["error"]
