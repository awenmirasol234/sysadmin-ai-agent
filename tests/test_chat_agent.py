"""Tests for multi-turn chat persistence, agent tools, hybrid ReAct loop, and chat REST endpoints."""

import json
from typing import Any, List, Optional

from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from backend.agent import chat_agent
from backend.agent.tools_registry import build_agent_tools, read_container_logs
from backend.db import (
    add_chat_message,
    create_chat_session,
    create_task,
    delete_chat_session,
    find_chat_session_by_task,
    get_approval,
    get_chat_session,
    get_task,
    list_chat_sessions,
)
from backend.main import app
from backend.tools.actions import create_approval_request


class ScriptedToolChatModel(BaseChatModel):
    """Minimal scripted BaseChatModel supporting bind_tools for deterministic ReAct tests."""

    responses: List[AIMessage] = Field(default_factory=list)
    seen_calls: List[List[BaseMessage]] = Field(default_factory=list)
    raise_on_call: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted-test-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedToolChatModel":
        return self

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen_calls.append(list(messages))
        if self.raise_on_call:
            raise RuntimeError("Simulated upstream LLM outage")
        idx = len(self.seen_calls) - 1
        msg = self.responses[idx] if idx < len(self.responses) else AIMessage(content="Summary complete.")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def test_chat_session_persistence_and_approval_hydration(monkeypatch):
    monkeypatch.setattr("backend.tools.actions.settings.ALLOWED_CONTAINERS", "web-app")

    session = create_chat_session(title="Incident triage")
    assert session["title"] == "Incident triage"

    task = create_task("Inspect web-app outage")
    appr = create_approval_request(
        action_type="restart_container",
        target="web-app",
        reason="Container exited unexpectedly",
        task_id=task.id,
    )

    add_chat_message(session["id"], "user", "Check why web-app stopped", task_id=task.id)
    add_chat_message(
        session["id"],
        "assistant",
        "Proposed restart for web-app.",
        task_id=task.id,
        tool_steps=[{"tool": "list_containers", "args": {}, "result_preview": "1 stopped", "status": "ok"}],
        approval_id=appr["approval_id"],
        mode="llm_react",
    )

    sessions = list_chat_sessions()
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 2

    loaded = get_chat_session(session["id"])
    assert loaded is not None
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][1]["tool_steps"][0]["tool"] == "list_containers"
    assert loaded["messages"][1]["approval"]["id"] == appr["approval_id"]
    assert loaded["messages"][1]["approval"]["status"] == "pending"

    assert find_chat_session_by_task(task_id=task.id) == session["id"]
    assert find_chat_session_by_task(approval_id=appr["approval_id"]) == session["id"]

    assert delete_chat_session(session["id"]) is True
    assert get_chat_session(session["id"]) is None


def test_tools_registry_tail_clamp_and_approval_guardrails(monkeypatch):
    captured_tails: List[int] = []

    def fake_get_logs(name: str, tail: int = 50):
        captured_tails.append(tail)
        return {"container": name, "logs": ["INFO ok"]}

    monkeypatch.setattr("backend.agent.tools_registry.get_container_logs", fake_get_logs)
    read_container_logs.invoke({"container_name": "web-app", "tail": 999})
    read_container_logs.invoke({"container_name": "web-app", "tail": -5})
    assert captured_tails == [200, 1]

    monkeypatch.setattr("backend.tools.actions.settings.ALLOWED_CONTAINERS", "web-app")
    task = create_task("Guardrail check")
    approval_sink = []
    tools = {t.name: t for t in build_agent_tools(task_id=task.id, approval_sink=approval_sink)}
    propose = tools["propose_container_action"]

    # Disallowed container is rejected cleanly without entering sink.
    blocked = json.loads(
        propose.invoke({"action_type": "stop_container", "target": "not-allowlisted", "reason": "Test block"})
    )
    assert "error" in blocked
    assert len(approval_sink) == 0

    # Allowed container succeeds once, and a second proposal in the same turn is rejected.
    first = json.loads(
        propose.invoke({"action_type": "restart_container", "target": "web-app", "reason": "Recover service"})
    )
    assert first["approval_id"]
    assert len(approval_sink) == 1

    second = json.loads(
        propose.invoke({"action_type": "restart_container", "target": "web-app", "reason": "Duplicate"})
    )
    assert "error" in second
    assert len(approval_sink) == 1


def test_react_chat_agent_multi_turn_tools_and_history(monkeypatch):
    monkeypatch.setattr(
        "backend.agent.tools_registry.list_docker_containers",
        lambda all=True: [{"id": "c1", "name": "web-app", "image": "nginx", "status": "exited", "state": "exited"}],
    )
    monkeypatch.setattr(
        "backend.agent.tools_registry.get_container_logs",
        lambda name, tail=50: {"container": name, "logs": ["ERROR bind failed"]},
    )
    monkeypatch.setattr("backend.tools.actions.settings.ALLOWED_CONTAINERS", "web-app")

    session = create_chat_session(title="Multi-turn session")
    task1 = create_task("Inspect web-app")
    add_chat_message(session["id"], "user", "Why is web-app down?", task_id=task1.id)

    turn1_model = ScriptedToolChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "list_containers", "args": {"include_stopped": True}, "id": "tc_1"}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "propose_container_action",
                        "args": {
                            "action_type": "restart_container",
                            "target": "web-app",
                            "reason": "Container web-app exited",
                        },
                        "id": "tc_2",
                    }
                ],
            ),
            AIMessage(content="Found `web-app` in exited state and queued a restart approval."),
        ]
    )

    res1 = chat_agent.run_chat_turn(session["id"], task1.id, "Why is web-app down?", model_override=turn1_model)
    assert res1["mode"] == "llm_react"
    assert len(res1["tool_steps"]) == 2
    assert res1["approval_id"] is not None
    assert get_task(task1.id)["status"] == "waiting_approval"

    # Turn 2 in the same thread must see Turn 1 HumanMessage + AIMessage without raw ToolMessages.
    task2 = create_task("Check logs for web-app")
    add_chat_message(session["id"], "user", "Show its recent logs", task_id=task2.id)

    turn2_model = ScriptedToolChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "read_container_logs", "args": {"container_name": "web-app", "tail": 20}, "id": "tc_3"}],
            ),
            AIMessage(content="Latest log line reports `ERROR bind failed`."),
        ]
    )

    res2 = chat_agent.run_chat_turn(session["id"], task2.id, "Show its recent logs", model_override=turn2_model)
    assert res2["mode"] == "llm_react"
    assert "ERROR bind failed" in res2["reply"]

    first_turn2_prompt = turn2_model.seen_calls[0]
    assert any(isinstance(m, HumanMessage) and "Why is web-app down?" in m.content for m in first_turn2_prompt)
    assert any(isinstance(m, AIMessage) and "queued a restart approval" in m.content for m in first_turn2_prompt)
    assert any(isinstance(m, HumanMessage) and "Show its recent logs" in m.content for m in first_turn2_prompt)


def test_react_chat_agent_respects_max_step_budget(monkeypatch):
    monkeypatch.setattr("backend.agent.tools_registry.list_docker_containers", lambda all=True: [])
    session = create_chat_session()
    task = create_task("Loop test")
    add_chat_message(session["id"], "user", "Check containers", task_id=task.id)

    looping_responses = [
        AIMessage(content="", tool_calls=[{"name": "list_containers", "args": {}, "id": f"tc_{i}"}])
        for i in range(chat_agent.MAX_REACT_STEPS + 4)
    ]
    model = ScriptedToolChatModel(responses=looping_responses)

    res = chat_agent.run_chat_turn(session["id"], task.id, "Check containers", model_override=model)
    assert res["mode"] == "llm_react"
    assert len(res["tool_steps"]) == chat_agent.MAX_REACT_STEPS - 1
    assert len(model.seen_calls) == chat_agent.MAX_REACT_STEPS + 1


def _mock_fallback_environment(monkeypatch, allowed_containers: str = "cache"):
    """Configures a hermetic host/container mock environment without live LLM credentials."""
    monkeypatch.setattr("backend.tools.actions.settings.ALLOWED_CONTAINERS", allowed_containers)
    monkeypatch.setattr("backend.agent.chat_agent.settings.LLM_PROVIDER", "openai")
    monkeypatch.setattr("backend.agent.chat_agent.settings.OPENAI_API_KEY", None)
    monkeypatch.setattr("backend.agent.chat_agent.settings.LLM_API_KEY", None)
    monkeypatch.setattr("backend.agent.chat_agent.settings.LLM_BASE_URL", None)
    monkeypatch.setattr(
        "backend.agent.nodes.get_system_metrics",
        lambda: {
            "cpu_usage_percent": 15.0,
            "memory_usage_percent": 40.0,
            "memory_used_gb": 6.4,
            "memory_total_gb": 16.0,
        },
    )
    monkeypatch.setattr(
        "backend.agent.nodes.get_disk_usage",
        lambda: {"disk_usage_percent": 25.0, "disk_used_gb": 25.0, "disk_total_gb": 100.0},
    )
    monkeypatch.setattr("backend.agent.nodes.get_uptime", lambda: {"uptime_human": "1d 2h"})
    monkeypatch.setattr(
        "backend.agent.nodes.evaluate_thresholds",
        lambda cpu, mem, disk: {"overall_status": "healthy", "alerts": []},
    )
    monkeypatch.setattr("backend.agent.nodes.list_docker_containers", lambda all=True: [])


def test_react_chat_agent_fallback_on_missing_creds_and_runtime_error(monkeypatch):
    _mock_fallback_environment(monkeypatch, allowed_containers="cache")

    session = create_chat_session()
    t1 = create_task("Health check")
    add_chat_message(session["id"], "user", "Run health check", task_id=t1.id)
    r1 = chat_agent.run_chat_turn(session["id"], t1.id, "Run health check")
    assert r1["mode"] == "fallback_rule"
    assert "Health" in r1["reply"] or "Report" in r1["reply"]

    # Case 2: runtime LLM error triggers deterministic fallback cleanly.
    t2 = create_task("Error recovery")
    add_chat_message(session["id"], "user", "Check host", task_id=t2.id)
    failing_model = ScriptedToolChatModel(raise_on_call=True)
    r2 = chat_agent.run_chat_turn(session["id"], t2.id, "Check host", model_override=failing_model)
    assert r2["mode"] == "fallback_rule"


def test_chat_rest_endpoints_and_remediation_sync(monkeypatch):
    _mock_fallback_environment(monkeypatch, allowed_containers="web-app,worker")

    client = TestClient(app)

    created = client.post("/api/chat/sessions", json={"title": "API ops thread"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    listed = client.get("/api/chat/sessions")
    assert listed.status_code == 200
    assert any(s["id"] == session_id for s in listed.json())

    sent = client.post(f"/api/chat/sessions/{session_id}/messages", json={"message": "Inspect host status"})
    assert sent.status_code == 200
    task_id = sent.json()["task_id"]

    detail = client.get(f"/api/chat/sessions/{session_id}")
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["mode"] == "fallback_rule"

    # Approval rejection sync appends a remediation confirmation message into the chat session.
    appr_rej = create_approval_request("restart_container", "web-app", "Test reject sync", task_id=task_id)
    rej_res = client.post(f"/api/approvals/{appr_rej['approval_id']}/reject")
    assert rej_res.status_code == 200
    assert get_approval(appr_rej["approval_id"])["status"] == "rejected"

    after_reject = client.get(f"/api/chat/sessions/{session_id}").json()["messages"]
    assert after_reject[-1]["mode"] == "remediation"
    assert "rejected" in after_reject[-1]["content"].lower()

    # Approval execution sync appends verification report into the chat session.
    appr_ok = create_approval_request("restart_container", "worker", "Test approve sync", task_id=task_id)
    monkeypatch.setattr(
        "backend.main.execute_approved_remediation",
        lambda tid, aid: {"final_report": "Verified worker container recovered cleanly."},
    )
    ok_res = client.post(f"/api/approvals/{appr_ok['approval_id']}/approve")
    assert ok_res.status_code == 200

    after_approve = client.get(f"/api/chat/sessions/{session_id}").json()["messages"]
    assert after_approve[-1]["mode"] == "remediation"
    assert "Verified worker container recovered cleanly." in after_approve[-1]["content"]

    deleted = client.delete(f"/api/chat/sessions/{session_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404
