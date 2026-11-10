"""AgentState schema definition for LangGraph workflow."""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    task_id: str
    user_request: str
    messages: Annotated[List[BaseMessage], operator.add]
    observations: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    proposed_actions: List[Dict[str, Any]]
    pending_approval_id: Optional[str]
    approval_status: Optional[str]  # "pending", "approved", "rejected"
    execution_results: List[Dict[str, Any]]
    verification_results: List[Dict[str, Any]]
    final_report: Optional[str]
    iteration: int
