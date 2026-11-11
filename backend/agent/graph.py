"""LangGraph StateGraph orchestration and execution entrypoints for SysAdmin AI Agent."""

from typing import Any, Dict
from langgraph.graph import END, StateGraph

from backend.agent.nodes import (
    analyze_results,
    decide_next_step,
    execute_action,
    execute_tools,
    generate_report,
    plan_investigation,
    understand_request,
)
from backend.agent.report import append_remediation_outcome
from backend.agent.state import AgentState
from backend.db import ensure_task, get_task, init_db, log_event, update_task_status


def build_agent_graph():
    """Builds and compiles the investigation StateGraph."""
    workflow = StateGraph(AgentState)

    workflow.add_node("understand_request", understand_request)
    workflow.add_node("plan_investigation", plan_investigation)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("analyze_results", analyze_results)
    workflow.add_node("decide_next_step", decide_next_step)
    workflow.add_node("generate_report", generate_report)

    workflow.set_entry_point("understand_request")
    workflow.add_edge("understand_request", "plan_investigation")
    workflow.add_edge("plan_investigation", "execute_tools")
    workflow.add_edge("execute_tools", "analyze_results")
    workflow.add_edge("analyze_results", "decide_next_step")
    workflow.add_edge("decide_next_step", "generate_report")
    workflow.add_edge("generate_report", END)

    return workflow.compile()


agent_graph = build_agent_graph()


def _create_initial_state(task_id: str, user_request: str, **kwargs) -> AgentState:
    """Initializes an AgentState dictionary with standard defaults."""
    state: AgentState = {
        "task_id": task_id,
        "user_request": user_request,
        "investigation_plan": [],
        "observations": [],
        "findings": [],
        "proposed_actions": [],
        "pending_approval_id": None,
        "approval_status": None,
        "execution_results": [],
        "final_report": None,
        "iteration": 0,
    }
    state.update(kwargs)
    return state


def run_investigation(task_id: str, user_request: str) -> Dict[str, Any]:
    """Runs a complete investigation cycle for a user task."""
    init_db()
    ensure_task(task_id, user_request)

    initial_state = _create_initial_state(task_id, user_request)
    return agent_graph.invoke(initial_state)


def execute_approved_remediation(task_id: str, approval_id: str) -> Dict[str, Any]:
    """Executes an authorized remediation and appends outcomes to the investigation report."""
    init_db()
    existing_task = get_task(task_id)

    resume_state = _create_initial_state(
        task_id,
        existing_task.get("user_request", "Execute approved remediation") if existing_task else "Execute approved remediation",
        pending_approval_id=approval_id,
        approval_status="approved",
    )

    exec_res = execute_action(resume_state)
    resume_state.update(exec_res)

    updated_report = append_remediation_outcome(
        existing_task.get("final_report") if existing_task else None,
        resume_state["execution_results"],
    )
    resume_state["final_report"] = updated_report

    all_succeeded = all(r.get("success", False) for r in resume_state["execution_results"])
    update_task_status(task_id, "completed" if all_succeeded else "failed", updated_report)
    log_event(task_id, "decision", "Updated task report with remediation outcome.")

    return resume_state
