"""Unit tests for dashboard API client contracts and API rejection handling."""

from unittest.mock import MagicMock

from backend.agent.graph import run_investigation
from backend.db import get_task
from backend.main import reject_action
from dashboard.api_client import APIClient


def test_api_client_accepts_limit_params(monkeypatch):
    captured_urls = []

    def fake_get(url, timeout=5):
        captured_urls.append(url)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        return resp

    monkeypatch.setattr("dashboard.api_client.requests.get", fake_get)

    client = APIClient(base_url="http://localhost:8000")
    assert client.get_incidents(limit=10) == []
    assert client.get_history(limit=20) == []
    assert captured_urls == [
        "http://localhost:8000/api/incidents?limit=10",
        "http://localhost:8000/api/history?limit=20",
    ]


def test_reject_action_updates_task_and_report(monkeypatch):
    monkeypatch.setattr(
        "backend.agent.nodes.list_docker_containers",
        lambda all=True: [
            {"id": "333", "name": "cache", "image": "redis", "status": "exited", "state": "exited", "created": ""},
        ],
    )
    monkeypatch.setattr(
        "backend.agent.nodes.get_container_details",
        lambda name: {"name": name, "exit_code": 1},
    )
    monkeypatch.setattr(
        "backend.agent.nodes.get_container_logs",
        lambda name, tail=50: {"logs": []},
    )

    task_id = "test-task-reject-01"
    result = run_investigation(task_id, "Inspect containers")
    approval_id = result["pending_approval_id"]
    assert approval_id is not None

    resp = reject_action(approval_id)
    assert resp["status"] == "rejected"

    task = get_task(task_id)
    assert task["status"] == "completed"
    assert "Action Rejected by User" in task["final_report"]
    assert "Container Stopped: cache" in task["final_report"]
