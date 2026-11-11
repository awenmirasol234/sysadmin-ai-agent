"""FastAPI REST API for SysAdmin AI Agent."""

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from backend.agent.chat_agent import run_chat_turn
from backend.agent.graph import execute_approved_remediation, run_investigation
from backend.agent.llm import get_chat_model, probe_model_connection
from backend.agent.report import append_rejection_outcome
from backend.config import settings
from backend.db import (
    add_chat_message,
    create_chat_session,
    create_task,
    delete_chat_session,
    find_chat_session_by_task,
    get_all_incidents,
    get_approval,
    get_chat_session,
    get_pending_approvals,
    get_task,
    get_task_events,
    get_task_history,
    init_db,
    list_chat_sessions,
    log_event,
    update_task_status,
)
from backend.tools.actions import decide_approval
from backend.tools.docker_tools import (
    get_container_details,
    get_container_logs,
    list_docker_containers,
)
from backend.tools.system import (
    get_disk_usage,
    get_load_average,
    get_network_info,
    get_system_info,
    get_system_metrics,
    get_uptime,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SysAdmin AI Agent API",
    description="REST API for autonomous server administration and container operations",
    version="1.0.0",
    lifespan=lifespan,
)

# Wildcard CORS requires credentials disabled; Streamlit calls this API server-side.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request & Response Models
class ChatRequest(BaseModel):
    message: str = Field(..., description="Natural language sysadmin instruction")


class ChatResponse(BaseModel):
    task_id: str
    status: str
    message: str


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., description="'approve' or 'reject'")


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(default="New conversation", description="Conversation thread title")


class ChatTurnRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Natural language conversational turn")


class ModelProbeRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@app.get("/api/health")
def get_health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "sysadmin-ai-backend",
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
    }


@app.get("/api/system/metrics")
def api_system_metrics() -> Dict[str, Any]:
    metrics = get_system_metrics()
    disk = get_disk_usage()
    uptime = get_uptime()
    net = get_network_info()
    load = get_load_average()
    return {
        "metrics": metrics,
        "disk": disk,
        "uptime": uptime,
        "network": net,
        "load_average": load,
    }


@app.get("/api/system/info")
def api_system_info() -> Dict[str, Any]:
    return get_system_info()


@app.get("/api/docker/containers")
def api_docker_containers() -> List[Dict[str, Any]]:
    return list_docker_containers(all=True)


@app.get("/api/docker/containers/{name}")
def api_container_details(name: str) -> Dict[str, Any]:
    details = get_container_details(name)
    if "error" in details and "not found" in details["error"].lower():
        raise HTTPException(status_code=404, detail=details["error"])
    return details


@app.get("/api/docker/containers/{name}/logs")
def api_container_logs(name: str, tail: int = 100) -> Dict[str, Any]:
    return get_container_logs(name, tail=tail)


def run_agent_task_worker(task_id: str, message: str):
    """Background worker executing the investigation workflow."""
    try:
        run_investigation(task_id, message)
    except Exception as e:
        # BackgroundTasks errors are invisible to the HTTP caller; persist failure for polling.
        log_event(task_id, "decision", f"Investigation failed with error: {str(e)}")
        update_task_status(task_id, "failed", f"Execution error: {str(e)}")


@app.post("/api/agent/chat", response_model=ChatResponse)
def submit_agent_task(req: ChatRequest, background_tasks: BackgroundTasks) -> ChatResponse:
    task = create_task(req.message)
    background_tasks.add_task(run_agent_task_worker, task.id, req.message)
    return ChatResponse(
        task_id=task.id,
        status="running",
        message="Starting server investigation.",
    )


@app.get("/api/agent/tasks/{id}")
def get_agent_task(id: str) -> Dict[str, Any]:
    task = get_task(id, include_events=False)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{id}' not found.")
    return task


@app.get("/api/agent/tasks/{id}/events")
def get_agent_task_events(id: str) -> List[Dict[str, Any]]:
    events = get_task_events(id)
    if events is None:
        raise HTTPException(status_code=404, detail=f"Task '{id}' not found.")
    return events


def run_chat_turn_worker(session_id: str, task_id: str, message: str):
    """Background worker executing one multi-turn agentic chat turn."""
    try:
        run_chat_turn(session_id, task_id, message)
    except Exception as e:
        log_event(task_id, "decision", f"Chat turn failed with error: {str(e)}")
        update_task_status(task_id, "failed", f"Execution error: {str(e)}")
        add_chat_message(
            session_id=session_id,
            role="assistant",
            content=f"Execution failed with error: {str(e)}",
            task_id=task_id,
            mode="error",
        )


@app.get("/api/chat/sessions")
def api_list_chat_sessions(limit: int = 30) -> List[Dict[str, Any]]:
    return list_chat_sessions(limit=limit)


@app.post("/api/chat/sessions")
def api_create_chat_session(req: Optional[CreateSessionRequest] = None) -> Dict[str, Any]:
    raw_title = req.title if req and req.title else "New conversation"
    title = raw_title.strip() or "New conversation"
    return create_chat_session(title=title)


@app.get("/api/chat/sessions/{session_id}")
def api_get_chat_session(session_id: str) -> Dict[str, Any]:
    session = get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Chat session '{session_id}' not found.")
    return session


@app.delete("/api/chat/sessions/{session_id}")
def api_delete_chat_session(session_id: str) -> Dict[str, Any]:
    deleted = delete_chat_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Chat session '{session_id}' not found.")
    return {"status": "deleted", "session_id": session_id}


@app.post("/api/chat/sessions/{session_id}/messages")
def api_send_chat_message(
    session_id: str,
    req: ChatTurnRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    if not get_chat_session(session_id):
        raise HTTPException(status_code=404, detail=f"Chat session '{session_id}' not found.")

    msg_text = req.message.strip()
    if not msg_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    task = create_task(msg_text)
    user_msg = add_chat_message(
        session_id=session_id,
        role="user",
        content=msg_text,
        task_id=task.id,
    )
    background_tasks.add_task(run_chat_turn_worker, session_id, task.id, msg_text)
    return {
        "session_id": session_id,
        "task_id": task.id,
        "status": "running",
        "message": "Agent turn started.",
        "user_message": user_msg,
    }


@app.get("/api/approvals")
def list_approvals() -> List[Dict[str, Any]]:
    return get_pending_approvals()


def execute_remediation_worker(task_id: str, approval_id: str):
    """Background worker executing approved remediation and updating task state."""
    try:
        result = execute_approved_remediation(task_id, approval_id)
        session_id = find_chat_session_by_task(task_id=task_id, approval_id=approval_id)
        if session_id:
            add_chat_message(
                session_id=session_id,
                role="assistant",
                content=result.get("final_report") or "Approved remediation completed.",
                task_id=task_id,
                mode="remediation",
            )
    except Exception as e:
        # Persist failure status so dashboard polling does not remain stuck on waiting_approval.
        log_event(task_id, "decision", f"Remediation failed: {str(e)}")
        update_task_status(task_id, "failed", f"Remediation error: {str(e)}")
        session_id = find_chat_session_by_task(task_id=task_id, approval_id=approval_id)
        if session_id:
            add_chat_message(
                session_id=session_id,
                role="assistant",
                content=f"Remediation failed: {str(e)}",
                task_id=task_id,
                mode="remediation",
            )


@app.post("/api/approvals/{id}/approve")
def approve_action(id: str, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    res = decide_approval(id, "approve")
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])

    appr = get_approval(id)
    task_id = res.get("task_id") or (appr.get("task_id") if appr else None) or "unknown"

    background_tasks.add_task(execute_remediation_worker, task_id, id)
    return {
        "status": "approved",
        "message": f"Action approved. Executing remediation and verifying recovery for {res.get('target')}.",
        "approval_id": id,
    }


@app.post("/api/approvals/{id}/reject")
def reject_action(id: str) -> Dict[str, Any]:
    res = decide_approval(id, "reject")
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])

    # Update the parent task so history reflects the rejection instead of remaining pending.
    task_id = res.get("task_id")
    if task_id:
        existing = get_task(task_id)
        log_event(task_id, "decision", f"User rejected proposed action '{res.get('action_type')}' on '{res.get('target')}'.")
        updated_report = append_rejection_outcome(
            existing.get("final_report") if existing else None,
            res.get("action_type", "action"),
            res.get("target", "target"),
        )
        update_task_status(task_id, "completed", updated_report)

    session_id = find_chat_session_by_task(task_id=task_id, approval_id=id)
    if session_id:
        action_type = res.get("action_type", "action")
        target = res.get("target", "target")
        add_chat_message(
            session_id=session_id,
            role="assistant",
            content=f"Proposed action `{action_type}` on `{target}` was rejected. Server state remains unchanged.",
            task_id=task_id,
            mode="remediation",
        )

    return {
        "status": "rejected",
        "message": "Action rejected. Server state remains unchanged.",
        "approval_id": id,
    }


@app.get("/api/incidents")
def list_incidents(limit: int = 50) -> List[Dict[str, Any]]:
    return get_all_incidents(limit=limit)


@app.get("/api/history")
def list_history(limit: int = 20) -> List[Dict[str, Any]]:
    return get_task_history(limit=limit)


@app.post("/api/model/probe")
def probe_model(req: ModelProbeRequest) -> Dict[str, Any]:
    # Return structured diagnostics rather than HTTP 500 so the UI displays provider errors inline.
    try:
        model = get_chat_model(
            provider=req.provider,
            model=req.model,
            api_key=req.api_key,
            base_url=req.base_url,
        )
        return probe_model_connection(model)
    except Exception as e:
        return {"success": False, "error": str(e)}
