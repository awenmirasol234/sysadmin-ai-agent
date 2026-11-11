"""Integration tests for LangGraph agent workflow."""

from unittest.mock import MagicMock

from backend.agent.graph import (
    build_agent_graph,
    execute_approved_remediation,
    run_investigation,
)
from backend.db import get_task, get_task_history
from backend.tools.actions import decide_approval


def test_agent_graph_compilation():
    graph = build_agent_graph()
    assert graph is not None
    assert "understand_request" in graph.nodes
    assert "plan_investigation" in graph.nodes
    assert "execute_tools" in graph.nodes
    assert "analyze_results" in graph.nodes
    assert "decide_next_step" in graph.nodes
    assert "generate_report" in graph.nodes


def test_run_investigation_e2e(monkeypatch):
    monkeypatch.setattr(
        "backend.agent.nodes.list_docker_containers",
        lambda all=True: [
            {"id": "111", "name": "api", "image": "python:3.12", "status": "running", "state": "running", "created": ""},
        ],
    )

    task_id = "test-task-e2e-01"
    result = run_investigation(task_id, "Check server health and docker containers")

    assert result["task_id"] == task_id
    assert len(result["observations"]) == 2
    assert "# SysAdmin AI — Investigation Report" in result["final_report"]

    history = get_task_history()
    task_record = next((t for t in history if t["id"] == task_id), None)
    assert task_record is not None
    assert task_record["status"] == "completed"


def test_waiting_approval_and_report_preservation(monkeypatch):
    monkeypatch.setattr(
        "backend.agent.nodes.list_docker_containers",
        lambda all=True: [
            {"id": "222", "name": "app-worker", "image": "alpine", "status": "exited", "state": "exited", "created": ""},
        ],
    )
    monkeypatch.setattr(
        "backend.agent.nodes.get_container_details",
        lambda name: {"name": name, "exit_code": 137},
    )
    monkeypatch.setattr(
        "backend.agent.nodes.get_container_logs",
        lambda name, tail=50: {"logs": ["Out of memory"]},
    )

    task_id = "test-task-approval-01"
    result = run_investigation(task_id, "Check server health and docker containers")

    assert result["pending_approval_id"] is not None
    assert result["approval_status"] == "pending"

    task_before = get_task(task_id)
    assert task_before["status"] == "waiting_approval"
    assert "Pending Human Approval" in task_before["final_report"]
    assert "Container Stopped: app-worker" in task_before["final_report"]

    mock_client = MagicMock()
    monkeypatch.setattr("backend.tools.actions.get_docker_client", lambda: mock_client)
    monkeypatch.setattr("backend.tools.actions.get_container_status", lambda target: "running")

    decide_approval(result["pending_approval_id"], "approve")
    remed = execute_approved_remediation(task_id, result["pending_approval_id"])

    task_after = get_task(task_id)
    assert task_after["status"] == "completed"
    assert "## 1. System Health Overview" in remed["final_report"]
    assert "Container Stopped: app-worker" in remed["final_report"]
    assert "Verification successful: Container 'app-worker' is now running." in remed["final_report"]
    assert "Pending Human Approval" not in remed["final_report"]
