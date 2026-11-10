"""LangGraph StateGraph orchestration and compilation for SysAdmin AI Agent."""

from typing import Any, Dict
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from backend.agent.nodes import (
    analyze_results,
    decide_next_step,
    execute_action,
    execute_tools,
    generate_report,
    plan_investigation,
    understand_request,
    verify_action,
)
from backend.agent.state import AgentState
from backend.db import (
    AgentTask,
    SessionLocal,
    create_task,
    get_task_history,
    init_db,
    update_task_status,
)


def route_after_decision(state: AgentState) -> str:
    """Routes based on approval state."""
    status = state.get("approval_status")
    if status == "approved":
        return "execute_action"
    # If no action needed or waiting for approval or rejected, proceed to report
    return "generate_report"


def build_agent_graph():
    """Builds and compiles the SysAdmin AI Agent StateGraph."""
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("understand_request", understand_request)
    workflow.add_node("plan_investigation", plan_investigation)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("analyze_results", analyze_results)
    workflow.add_node("decide_next_step", decide_next_step)
    workflow.add_node("execute_action", execute_action)
    workflow.add_node("verify_action", verify_action)
    workflow.add_node("generate_report", generate_report)

    # Define edges
    workflow.set_entry_point("understand_request")
    workflow.add_edge("understand_request", "plan_investigation")
    workflow.add_edge("plan_investigation", "execute_tools")
    workflow.add_edge("execute_tools", "analyze_results")
    workflow.add_edge("analyze_results", "decide_next_step")

    # Conditional routing after decision
    workflow.add_conditional_edges(
        "decide_next_step",
        route_after_decision,
        {
            "execute_action": "execute_action",
            "generate_report": "generate_report",
        },
    )

    workflow.add_edge("execute_action", "verify_action")
    workflow.add_edge("verify_action", "generate_report")
    workflow.add_edge("generate_report", END)

    # Use checkpointer for state persistence
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# Singleton compiled graph instance
agent_graph = build_agent_graph()


def run_investigation(task_id: str, user_request: str) -> Dict[str, Any]:
    """Runs a complete investigation cycle for a user task."""
    init_db()
    with SessionLocal() as db:
        existing = db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if not existing:
            db_task = AgentTask(id=task_id, user_request=user_request, status="running")
            db.add(db_task)
            db.commit()

    initial_state: AgentState = {
        "task_id": task_id,
        "user_request": user_request,
        "messages": [],
        "observations": [],
        "findings": [],
        "proposed_actions": [],
        "pending_approval_id": None,
        "approval_status": None,
        "execution_results": [],
        "verification_results": [],
        "final_report": None,
        "iteration": 0,
    }

    config = {"configurable": {"thread_id": task_id}}
    result_state = agent_graph.invoke(initial_state, config=config)
    return result_state


def execute_approved_remediation(task_id: str, approval_id: str) -> Dict[str, Any]:
    """Resumes the workflow to execute an authorized remediation and verify outcome."""
    init_db()
    resume_state: AgentState = {
        "task_id": task_id,
        "user_request": "Execute approved remediation",
        "messages": [],
        "observations": [],
        "findings": [],
        "proposed_actions": [],
        "pending_approval_id": approval_id,
        "approval_status": "approved",
        "execution_results": [],
        "verification_results": [],
        "final_report": None,
        "iteration": 0,
    }

    # Execute action node directly
    exec_res = execute_action(resume_state)
    resume_state.update(exec_res)

    # Verify action node
    ver_res = verify_action(resume_state)
    resume_state.update(ver_res)

    # Generate final updated report
    rep_res = generate_report(resume_state)
    resume_state.update(rep_res)

    return resume_state
