"""Unit tests for Docker tools and log sanitization."""

from backend.tools.docker_tools import (
    get_container_details,
    get_container_status,
    list_docker_containers,
    sanitize_log_text,
)


def test_sanitize_log_text():
    raw = "2026-11-10 [INFO] Connecting with password=SuperSecret123 and token=abcXYZ987"
    sanitized = sanitize_log_text(raw)
    assert "SuperSecret123" not in sanitized
    assert "abcXYZ987" not in sanitized
    assert "password=[REDACTED]" in sanitized
    assert "token=[REDACTED]" in sanitized

    bearer_raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
    sanitized_bearer = sanitize_log_text(bearer_raw)
    assert "eyJhbG" not in sanitized_bearer
    assert "Bearer [REDACTED]" in sanitized_bearer


def test_list_docker_containers():
    containers = list_docker_containers(all=True)
    assert isinstance(containers, list)
    if containers:
        first = containers[0]
        assert "name" in first
        assert "status" in first
        assert "id" in first


def test_get_nonexistent_container_status():
    status = get_container_status("definitely-nonexistent-container-xyz")
    assert status == "not_found"

    details = get_container_details("definitely-nonexistent-container-xyz")
    assert "error" in details
