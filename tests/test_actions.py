"""Unit tests for action security, allowlist validation, and approval token lifecycle."""

from unittest.mock import MagicMock
import pytest

from backend.config import settings
from backend.tools.actions import (
    SecurityError,
    compute_action_hash,
    create_approval_request,
    decide_approval,
    execute_approved_action,
    validate_target,
)


@pytest.fixture(autouse=True)
def restore_allowed_containers():
    orig_allowed = settings.ALLOWED_CONTAINERS
    settings.ALLOWED_CONTAINERS = ["*"]
    yield
    settings.ALLOWED_CONTAINERS = orig_allowed


def test_validate_target_allowed():
    settings.ALLOWED_CONTAINERS = ["*"]
    validate_target("restart_container", "production-api")
    validate_target("start_container", "redis-cache")
    validate_target("stop_container", "worker-service")

    settings.ALLOWED_CONTAINERS = ["app-frontend", "app-backend"]
    validate_target("restart_container", "app-frontend")
    validate_target("start_container", "app-backend")


def test_validate_target_forbidden():
    settings.ALLOWED_CONTAINERS = ["*"]
    with pytest.raises(SecurityError) as exc_info:
        validate_target("restart_container", "sysadmin-backend")
    assert "protected SysAdmin system component" in str(exc_info.value)

    with pytest.raises(SecurityError) as exc_info:
        validate_target("stop_container", "sysadmin-dashboard")
    assert "protected SysAdmin system component" in str(exc_info.value)

    settings.ALLOWED_CONTAINERS = ["app-frontend"]
    with pytest.raises(SecurityError) as exc_info:
        validate_target("restart_container", "unauthorized-prod-db")
    assert "NOT in the allowed containers allowlist" in str(exc_info.value)

    with pytest.raises(SecurityError):
        validate_target("restart_container", "app-frontend; rm -rf /")

    with pytest.raises(SecurityError) as exc_info:
        validate_target("delete_database", "app-frontend")
    assert "Unsupported action type" in str(exc_info.value)

    with pytest.raises(SecurityError) as exc_info:
        validate_target("restart_service", "docker")
    assert "Unsupported action type" in str(exc_info.value)


def test_compute_action_hash():
    h1 = compute_action_hash("restart_container", "nginx")
    h2 = compute_action_hash("restart_container", "nginx")
    h3 = compute_action_hash("restart_container", "redis")

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_approval_lifecycle():
    req = create_approval_request(
        action_type="restart_container",
        target="nginx",
        reason="Nginx container is stopped.",
    )
    approval_id = req["approval_id"]
    assert req["status"] == "pending"

    dec = decide_approval(approval_id, "reject")
    assert dec["status"] == "rejected"

    res = execute_approved_action(approval_id)
    assert "Cannot execute" in res["error"]


def test_approval_replay_protection(monkeypatch):
    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    monkeypatch.setattr("backend.tools.actions.get_docker_client", lambda: mock_client)
    monkeypatch.setattr("backend.tools.actions.get_container_status", lambda target: "running")

    req = create_approval_request(
        action_type="restart_container",
        target="nginx",
        reason="Nginx container is stopped.",
    )
    approval_id = req["approval_id"]
    decide_approval(approval_id, "approve")

    res = execute_approved_action(approval_id)
    assert res["success"] is True
    mock_container.restart.assert_called_once_with(timeout=10)

    re_exec = execute_approved_action(approval_id)
    assert "Security violation" in re_exec["error"]
