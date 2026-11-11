"""AgentState schema definition for LangGraph workflow."""

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict):
    task_id: str
    user_request: str
    investigation_plan: List[str]
    observations: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    proposed_actions: List[Dict[str, Any]]
    pending_approval_id: Optional[str]
    approval_status: Optional[str]  # "pending", "approved", "rejected"
    execution_results: List[Dict[str, Any]]
    final_report: Optional[str]
    iteration: int
