"""Integration tests for LangGraph agent workflow."""

from backend.agent.graph import agent_graph, build_agent_graph, run_investigation
from backend.db import get_task_history, init_db


def test_agent_graph_compilation():
    graph = build_agent_graph()
    assert graph is not None
    # Graph nodes should exist
    assert "understand_request" in graph.nodes
    assert "plan_investigation" in graph.nodes
    assert "execute_tools" in graph.nodes
    assert "analyze_results" in graph.nodes
    assert "decide_next_step" in graph.nodes
    assert "generate_report" in graph.nodes


def test_run_investigation_e2e():
    init_db()
    task_id = "test-task-e2e-01"
    result = run_investigation(task_id, "Check server health and docker containers")

    assert result["task_id"] == task_id
    assert "observations" in result
    assert len(result["observations"]) >= 1
    assert "final_report" in result
    assert isinstance(result["final_report"], str)
    assert "# SysAdmin AI — Investigation Report" in result["final_report"]

    # Verify task in database
    history = get_task_history()
    task_record = next((t for t in history if t["id"] == task_id), None)
    assert task_record is not None
    assert task_record["status"] in ("completed", "waiting_approval")
