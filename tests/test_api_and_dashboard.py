"""Unit tests for dashboard API client contracts and API rejection handling."""

from pathlib import Path
from unittest.mock import MagicMock

from streamlit.testing.v1 import AppTest

from backend.agent.graph import run_investigation
from backend.db import get_task
from backend.main import reject_action
from dashboard.api_client import APIClient, api as dashboard_api
from dashboard.components import (
    build_approval_dossier,
    build_chat_mode_notice,
    build_container_inspector_summary,
    build_host_header,
    build_tool_steps_summary,
)
from dashboard.theme import format_status_label, threshold_tone


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


def test_api_client_container_details_and_probe_payload(monkeypatch):
    get_urls = []
    post_calls = []

    def fake_get(url, timeout=5):
        get_urls.append(url)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"name": "api", "status": "running"}
        return resp

    def fake_post(url, json=None, timeout=5):
        post_calls.append((url, json, timeout))
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": True, "response": "PONG"}
        return resp

    monkeypatch.setattr("dashboard.api_client.requests.get", fake_get)
    monkeypatch.setattr("dashboard.api_client.requests.post", fake_post)

    client = APIClient(base_url="http://localhost:8000")
    details = client.get_container_details("my/container")
    assert details["status"] == "running"
    assert get_urls == ["http://localhost:8000/api/docker/containers/my%2Fcontainer"]

    client.probe_model("openai", "gpt-4o-mini")
    client.probe_model("openai-compatible", "9r-model", api_key="secret", base_url="http://localhost:20128/v1")
    assert post_calls == [
        ("http://localhost:8000/api/model/probe", {"provider": "openai", "model": "gpt-4o-mini"}, 10),
        (
            "http://localhost:8000/api/model/probe",
            {
                "provider": "openai-compatible",
                "model": "9r-model",
                "api_key": "secret",
                "base_url": "http://localhost:20128/v1",
            },
            10,
        ),
    ]


def test_dashboard_components_escape_html_and_format_status():
    assert format_status_label("waiting_approval") == "Waiting approval"
    assert format_status_label("tool_call") == "Tool call"
    assert threshold_tone(92.0, 70.0, 90.0) == "critical"
    assert threshold_tone(75.0, 70.0, 90.0) == "warning"

    xss = "<script>alert(1)</script>"
    header_html = build_host_header({"hostname": xss, "os": "Linux"}, {"status": "healthy", "provider": "openai", "model": "gpt-4o-mini"}, "2h 1m")
    assert "<script>" not in header_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in header_html

    inspector_html = build_container_inspector_summary({"name": xss, "status": "exited", "image": "redis", "ports": []})
    assert "<script>" not in inspector_html

    dossier_html = build_approval_dossier({"id": "a1", "action_type": "restart_container", "target": "api", "reason": xss})
    assert "<script>" not in dossier_html

    tools_html = build_tool_steps_summary([{"tool": "inspect_container", "args": {"container_name": xss}, "result_preview": xss, "status": "ok"}])
    assert "<script>" not in tools_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in tools_html

    assert "fallback mode" in build_chat_mode_notice("fallback_rule").lower()
    assert build_chat_mode_notice("llm_react") == ""


def test_dashboard_app_renders_with_mocked_api(monkeypatch):
    monkeypatch.setattr(dashboard_api, "get_health", lambda: {"status": "healthy", "provider": "openai", "model": "gpt-4o-mini"})
    monkeypatch.setattr(dashboard_api, "get_system_info", lambda: {"hostname": "prod-node-1", "os": "Linux", "os_release": "6.8", "architecture": "x86_64", "cpu_count_logical": 4, "cpu_count_physical": 2})
    monkeypatch.setattr(dashboard_api, "get_system_metrics", lambda: {
        "metrics": {"cpu_usage_percent": 32.5, "cpu_per_core": [20.0, 45.0, 30.0, 35.0], "memory_usage_percent": 54.0, "memory_used_gb": 8.6, "memory_total_gb": 16.0, "swap_usage_percent": 1.0, "swap_used_gb": 0.1, "swap_total_gb": 4.0},
        "disk": {"path": "/", "disk_usage_percent": 41.2, "disk_used_gb": 41.2, "disk_total_gb": 100.0},
        "uptime": {"uptime_human": "4d 3h 12m"},
        "load_average": {"load_1m": 0.42, "load_5m": 0.38, "load_15m": 0.31},
        "network": {"bytes_sent_mb": 120.5, "bytes_recv_mb": 240.8, "packets_sent": 1000, "packets_recv": 1500, "interfaces": ["eth0", "lo"]},
    })
    monkeypatch.setattr(dashboard_api, "get_incidents", lambda limit=10: [])
    monkeypatch.setattr(dashboard_api, "get_containers", lambda: [{"id": "abc123", "name": "worker", "status": "running", "image": "app:latest", "created": "2026-11-11T00:00:00Z"}])
    monkeypatch.setattr(dashboard_api, "get_container_details", lambda name: {"id": "abc123", "name": name, "image": "app:latest", "status": "running", "health": "healthy", "exit_code": 0, "restart_count": 0, "ports": ["8000/tcp"], "started_at": "2026-11-11T00:00:00Z"})
    monkeypatch.setattr(dashboard_api, "get_container_logs", lambda name, tail=50: {"logs": ["INFO Server listening"]})
    monkeypatch.setattr(dashboard_api, "get_pending_approvals", lambda: [])
    monkeypatch.setattr(dashboard_api, "get_history", lambda limit=30: [])

    created_sessions = []
    sent_messages = []
    monkeypatch.setattr(dashboard_api, "list_chat_sessions", lambda limit=30: list(created_sessions))

    def fake_create_session(title="New conversation"):
        s = {"id": "sess-1", "title": title, "message_count": 0, "messages": []}
        created_sessions.append(s)
        return s

    def fake_send_message(session_id, message):
        sent_messages.append((session_id, message))
        return {"session_id": session_id, "task_id": "task-starter-1", "status": "running"}

    monkeypatch.setattr(dashboard_api, "create_chat_session", fake_create_session)
    monkeypatch.setattr(dashboard_api, "get_chat_session", lambda sid: {"id": sid, "title": "New conversation", "messages": []})
    monkeypatch.setattr(dashboard_api, "send_chat_message", fake_send_message)
    monkeypatch.setattr(dashboard_api, "get_task", lambda tid: {"id": tid, "status": "completed", "started_at": "2026-11-11T00:00:00Z"})
    monkeypatch.setattr(dashboard_api, "get_task_events", lambda tid: [])

    app_path = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
    at = AppTest.from_file(app_path).run(timeout=15)
    assert not at.exception
    assert len(at.tabs) == 6

    # Clicking an Assistant starter prompt creates a session and sends the conversational turn.
    at.button(key="starter_prompt_0").click().run(timeout=15)
    assert not at.exception
    assert at.session_state["active_chat_session_id"] == "sess-1"
    assert len(sent_messages) == 1
    assert "health check" in sent_messages[0][1].lower()

    # Submitting via inline st.chat_input appends another turn to the same session.
    at.chat_input[0].set_value("Check worker logs").run(timeout=15)
    assert not at.exception
    assert len(sent_messages) == 2
    assert sent_messages[1] == ("sess-1", "Check worker logs")


def test_dashboard_app_renders_populated_incidents_approvals_and_history(monkeypatch):
    monkeypatch.setattr(dashboard_api, "get_health", lambda: {"status": "healthy", "provider": "openai-compatible", "model": "deepseek-chat"})
    monkeypatch.setattr(dashboard_api, "get_system_info", lambda: {"hostname": "prod-node-2", "os": "Linux", "os_release": "6.8", "architecture": "x86_64", "cpu_count_logical": 2, "cpu_count_physical": 2})
    monkeypatch.setattr(dashboard_api, "get_system_metrics", lambda: {
        "metrics": {"cpu_usage_percent": 91.5, "cpu_per_core": [92.0, 91.0], "memory_usage_percent": 82.0, "memory_used_gb": 13.1, "memory_total_gb": 16.0, "swap_usage_percent": 15.0, "swap_used_gb": 0.6, "swap_total_gb": 4.0},
        "disk": {"path": "/host/root", "disk_usage_percent": 85.0, "disk_used_gb": 85.0, "disk_total_gb": 100.0},
        "uptime": {"uptime_human": "12d 1h"},
        "load_average": {"load_1m": 2.4, "load_5m": 1.9, "load_15m": 1.4},
        "network": {"bytes_sent_mb": 400.0, "bytes_recv_mb": 820.0, "packets_sent": 5000, "packets_recv": 9000, "interfaces": ["eth0", "docker0"]},
    })
    monkeypatch.setattr(dashboard_api, "get_incidents", lambda limit=10: [
        {"severity": "critical", "component": "system", "title": "High Resource Usage Detected", "status": "open", "created_at": "2026-11-11T05:00:00Z"}
    ])
    monkeypatch.setattr(dashboard_api, "get_containers", lambda: [
        {"id": "def456", "name": "cache", "status": "exited", "image": "redis:7", "created": "2026-11-11T04:00:00Z"}
    ])
    monkeypatch.setattr(dashboard_api, "get_container_details", lambda name: {
        "id": "def456", "name": name, "image": "redis:7", "status": "exited", "health": "none", "exit_code": 137, "restart_count": 2, "ports": [], "started_at": "2026-11-11T04:00:00Z", "error": "OOMKilled"
    })
    monkeypatch.setattr(dashboard_api, "get_container_logs", lambda name, tail=50: {"logs": []})
    monkeypatch.setattr(dashboard_api, "get_pending_approvals", lambda: [
        {"id": "appr-123", "action_type": "restart_container", "target": "cache", "reason": "Container exited with 137", "created_at": "2026-11-11T05:01:00Z", "expires_at": "2026-11-11T05:06:00Z"}
    ])
    monkeypatch.setattr(dashboard_api, "get_history", lambda limit=30: [
        {"id": "task-1", "user_request": "Inspect containers", "status": "waiting_approval", "started_at": "2026-11-11T05:00:00Z", "final_report": "# Report\nPending approval", "events": [{"event_type": "approval_request", "description": "Created approval"}]}
    ])
    monkeypatch.setattr(dashboard_api, "get_task", lambda tid: {"id": tid, "status": "waiting_approval", "started_at": "2026-11-11T05:00:00Z", "final_report": "# Investigation Report\nAwaiting approval."})
    monkeypatch.setattr(dashboard_api, "get_task_events", lambda tid: [{"event_type": "tool_call", "created_at": "2026-11-11T05:00:01Z", "description": "Listed containers"}])

    approved_calls = []
    monkeypatch.setattr(dashboard_api, "approve_action", lambda aid: approved_calls.append(aid) or {"status": "approved", "message": "Executed"})
    monkeypatch.setattr(dashboard_api, "list_chat_sessions", lambda limit=30: [{"id": "sess-99", "title": "Inspect containers", "message_count": 2}])
    monkeypatch.setattr(dashboard_api, "get_chat_session", lambda sid: {
        "id": sid,
        "title": "Inspect containers",
        "messages": [
            {"id": "m1", "role": "user", "content": "Inspect containers", "task_id": "task-1", "tool_steps": []},
            {
                "id": "m2",
                "role": "assistant",
                "content": "Found exited container `cache`. Requesting restart.",
                "task_id": "task-1",
                "mode": "llm_react",
                "tool_steps": [
                    {"tool": "list_containers", "args": {"include_stopped": True}, "result_preview": "1 exited container", "status": "ok"}
                ],
                "approval_id": "appr-123",
                "approval": {
                    "id": "appr-123",
                    "task_id": "task-1",
                    "status": "pending",
                    "action_type": "restart_container",
                    "target": "cache",
                    "reason": "Container exited with 137",
                    "created_at": "2026-11-11T05:01:00Z",
                    "expires_at": "2026-11-11T05:06:00Z",
                },
            },
        ],
    })

    app_path = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
    at = AppTest.from_file(app_path)
    at.session_state["active_task_id"] = "task-1"
    at.run(timeout=15)
    assert not at.exception
    assert any(b.key == "appr_appr-123" for b in at.button)
    assert any(b.key == "rej_appr-123" for b in at.button)
    assert any(b.key == "chat_appr_appr-123" for b in at.button)
    assert any(b.key == "chat_rej_appr-123" for b in at.button)

    # Inline authorization button inside Assistant chat triggers approval endpoint cleanly.
    at.button(key="chat_appr_appr-123").click().run(timeout=15)
    assert not at.exception
    assert approved_calls == ["appr-123"]
