"""SQLite database engine, SQLAlchemy models, and audit persistence repository."""

from datetime import datetime, timezone
import json
from typing import Any, Callable, Dict, List, Optional
import uuid
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    desc,
)
from sqlalchemy.orm import declarative_base, joinedload, relationship, sessionmaker
from backend.config import settings

Base = declarative_base()


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_request = Column(Text, nullable=False)
    status = Column(String(32), default="running")  # running, waiting_approval, completed, failed
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    final_report = Column(Text, nullable=True)

    events = relationship("AgentEvent", back_populates="task", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="task", cascade="all, delete-orphan")
    approvals = relationship("ActionApproval", back_populates="task", cascade="all, delete-orphan")

    def to_dict(self, include_events: bool = True) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "user_request": self.user_request,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "final_report": self.final_report,
        }
        if include_events:
            data["events"] = [e.to_dict() for e in self.events]
        return data


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("agent_tasks.id"), index=True, nullable=False)
    event_type = Column(String(32), nullable=False)  # tool_call, decision, approval_request
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("AgentTask", back_populates="events")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("agent_tasks.id"), nullable=True)
    severity = Column(String(16), default="warning")  # info, warning, critical
    component = Column(String(32), nullable=False)  # docker, system
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(16), default="open")  # open, resolved, dismissed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("AgentTask", back_populates="incidents")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "severity": self.severity,
            "component": self.component,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ActionApproval(Base):
    __tablename__ = "action_approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("agent_tasks.id"), nullable=True)
    action_type = Column(String(32), nullable=False)  # restart_container, start_container, stop_container
    target = Column(String(128), nullable=False)
    arguments_hash = Column(String(64), nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(16), default="pending")  # pending, approved, rejected, expired, executed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    decided_at = Column(DateTime, nullable=True)

    task = relationship("AgentTask", back_populates="approvals")
    executions = relationship("ActionExecution", back_populates="approval", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "action_type": self.action_type,
            "target": self.target,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class ActionExecution(Base):
    __tablename__ = "action_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_id = Column(String(36), ForeignKey("action_approvals.id"), nullable=False)
    action_type = Column(String(32), nullable=False)
    target = Column(String(128), nullable=False)
    result = Column(Text, nullable=False)
    success = Column(Boolean, default=False)
    verification = Column(Text, nullable=True)
    executed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    approval = relationship("ActionApproval", back_populates="executions")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(160), default="New conversation", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        order_by="ChatMessage.id",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_messages: bool = False, approval_map: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "message_count": len(self.messages),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_messages:
            data["messages"] = [m.to_dict(approval_map=approval_map) for m in self.messages]
        return data


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), index=True, nullable=False)
    task_id = Column(String(36), ForeignKey("agent_tasks.id"), index=True, nullable=True)
    role = Column(String(16), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    tool_steps_json = Column(Text, nullable=True)
    approval_id = Column(String(36), nullable=True)
    mode = Column(String(24), nullable=True)  # llm_react, fallback_rule, remediation
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("ChatSession", back_populates="messages")

    def to_dict(self, approval_map: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        tool_steps: List[Dict[str, Any]] = []
        if self.tool_steps_json:
            try:
                parsed = json.loads(self.tool_steps_json)
                if isinstance(parsed, list):
                    tool_steps = parsed
            except json.JSONDecodeError:
                tool_steps = []
        data: Dict[str, Any] = {
            "id": self.id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "role": self.role,
            "content": self.content,
            "tool_steps": tool_steps,
            "approval_id": self.approval_id,
            "mode": self.mode,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if self.approval_id and approval_map and self.approval_id in approval_map:
            data["approval"] = approval_map[self.approval_id]
        return data


# FastAPI runs sync endpoints and BackgroundTasks across threads, which SQLite blocks unless disabled.
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Creates all database tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    """Checks whether an expiration timestamp has passed in UTC."""
    # SQLite drops tzinfo on DateTime columns; normalize naive DB values back to UTC.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now


# Repository Helpers
def create_task(user_request: str) -> AgentTask:
    """Creates and persists a new running agent task."""
    with SessionLocal() as db:
        task = AgentTask(user_request=user_request, status="running")
        db.add(task)
        db.commit()
        db.refresh(task)
        return task


def ensure_task(task_id: str, user_request: str) -> AgentTask:
    """Creates a task row only if missing, supporting caller-supplied IDs in CLI/tests."""
    with SessionLocal() as db:
        existing = db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if existing:
            return existing
        task = AgentTask(id=task_id, user_request=user_request, status="running")
        db.add(task)
        db.commit()
        db.refresh(task)
        return task


def get_task(task_id: str, include_events: bool = False) -> Optional[Dict[str, Any]]:
    """Fetches a serialized task by ID, or None if not found."""
    with SessionLocal() as db:
        query = db.query(AgentTask)
        if include_events:
            query = query.options(joinedload(AgentTask.events))
        task = query.filter(AgentTask.id == task_id).first()
        return task.to_dict(include_events=include_events) if task else None


def get_task_events(task_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetches ordered audit events for a task, or None if the task does not exist."""
    with SessionLocal() as db:
        task = (
            db.query(AgentTask)
            .options(joinedload(AgentTask.events))
            .filter(AgentTask.id == task_id)
            .first()
        )
        if not task:
            return None
        return [e.to_dict() for e in task.events]


def update_task_status(task_id: str, status: str, final_report: Optional[str] = None):
    """Updates task status, optional report text, and completion timestamp."""
    with SessionLocal() as db:
        task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if task:
            task.status = status
            # Explicit None check lets callers preserve or clear empty strings intentionally.
            if final_report is not None:
                task.final_report = final_report
            if status in ("completed", "failed"):
                task.completed_at = datetime.now(timezone.utc)
            db.commit()


def log_event(task_id: str, event_type: str, description: str):
    with SessionLocal() as db:
        event = AgentEvent(task_id=task_id, event_type=event_type, description=description)
        db.add(event)
        db.commit()


def record_incident(
    component: str,
    title: str,
    description: str,
    severity: str = "warning",
    task_id: Optional[str] = None,
) -> Incident:
    with SessionLocal() as db:
        incident = Incident(
            task_id=task_id,
            component=component,
            title=title,
            description=description,
            severity=severity,
            status="open",
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        return incident


def get_all_incidents(limit: int = 50) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        items = db.query(Incident).order_by(desc(Incident.created_at)).limit(limit).all()
        return [i.to_dict() for i in items]


def get_pending_approvals() -> List[Dict[str, Any]]:
    """Returns active pending approvals after lazily marking expired items."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        pending = (
            db.query(ActionApproval)
            .filter(ActionApproval.status == "pending")
            .order_by(desc(ActionApproval.created_at))
            .all()
        )
        active = []
        dirty = False
        for item in pending:
            if _is_expired(item.expires_at, now):
                item.status = "expired"
                dirty = True
            else:
                active.append(item.to_dict())
        if dirty:
            db.commit()
        return active


def create_approval_record(
    approval_id: str,
    action_type: str,
    target: str,
    arguments_hash: str,
    reason: str,
    created_at: datetime,
    expires_at: datetime,
    task_id: Optional[str] = None,
) -> None:
    with SessionLocal() as db:
        approval = ActionApproval(
            id=approval_id,
            task_id=task_id,
            action_type=action_type,
            target=target,
            arguments_hash=arguments_hash,
            reason=reason,
            status="pending",
            created_at=created_at,
            expires_at=expires_at,
        )
        db.add(approval)
        db.commit()


def get_approval(approval_id: str) -> Optional[Dict[str, Any]]:
    with SessionLocal() as db:
        approval = db.query(ActionApproval).filter(ActionApproval.id == approval_id).first()
        return approval.to_dict() if approval else None


def decide_approval_record(approval_id: str, decision_clean: str, now: datetime) -> Dict[str, Any]:
    with SessionLocal() as db:
        approval = db.query(ActionApproval).filter(ActionApproval.id == approval_id).first()
        if not approval:
            return {"error": f"Approval request '{approval_id}' not found."}

        if approval.status != "pending":
            return {"error": f"Approval request '{approval_id}' is already {approval.status}."}

        if _is_expired(approval.expires_at, now):
            approval.status = "expired"
            db.commit()
            return {"error": f"Approval request '{approval_id}' has expired."}

        approval.status = "approved" if decision_clean == "approve" else "rejected"
        approval.decided_at = now
        db.commit()

        return {
            "approval_id": approval_id,
            "task_id": approval.task_id,
            "status": approval.status,
            "action_type": approval.action_type,
            "target": approval.target,
        }


def prepare_approval_execution(
    approval_id: str,
    now: datetime,
    validate_fn: Callable[[str, str], None],
    hash_fn: Callable[[str, str], str],
) -> Dict[str, Any]:
    """Validates an approval record before executing an action.

    Args:
        approval_id: Approval UUID token to authorize.
        now: Current UTC timestamp for expiration checks.
        validate_fn: Policy validator raising on disallowed action/target.
        hash_fn: Fingerprint generator matching stored arguments_hash.

    Returns:
        Dict with ``action_type`` and ``target`` when valid, or ``error``.
    """
    with SessionLocal() as db:
        approval = db.query(ActionApproval).filter(ActionApproval.id == approval_id).first()
        if not approval:
            return {"error": f"Approval '{approval_id}' not found."}

        if approval.status == "executed":
            return {"error": f"Security violation: Approval token '{approval_id}' has already been executed."}

        if approval.status != "approved":
            return {"error": f"Cannot execute: Approval status is '{approval.status}', expected 'approved'."}

        if _is_expired(approval.expires_at, now):
            approval.status = "expired"
            db.commit()
            return {"error": "Approval token has expired."}

        # Re-validate allowlist and hash at execution time in case policy changed since approval.
        try:
            validate_fn(approval.action_type, approval.target)
        except Exception as exc:
            approval.status = "rejected"
            db.commit()
            return {"error": f"Security check failed: {exc}"}

        if approval.arguments_hash != hash_fn(approval.action_type, approval.target):
            approval.status = "rejected"
            db.commit()
            return {"error": "Security violation: Action arguments fingerprint does not match approved token."}

        return {
            "action_type": approval.action_type,
            "target": approval.target,
        }


def complete_approval_execution(
    approval_id: str,
    action_type: str,
    target: str,
    result: str,
    success: bool,
    verification: str,
    executed_at: datetime,
) -> None:
    """Marks an approval executed and persists the execution audit record."""
    with SessionLocal() as db:
        approval = db.query(ActionApproval).filter(ActionApproval.id == approval_id).first()
        if approval:
            # Invalidate the token immediately after the execution attempt to prevent replays.
            approval.status = "executed"
        db.add(
            ActionExecution(
                approval_id=approval_id,
                action_type=action_type,
                target=target,
                result=result,
                success=success,
                verification=verification,
                executed_at=executed_at,
            )
        )
        db.commit()


def get_task_history(limit: int = 20) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        tasks = (
            db.query(AgentTask)
            .options(joinedload(AgentTask.events))
            .order_by(desc(AgentTask.started_at))
            .limit(limit)
            .all()
        )
        return [t.to_dict() for t in tasks]


def create_chat_session(
    title: str = "New conversation",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates and persists a conversational chat session."""
    clean_title = (title or "New conversation").strip()[:160] or "New conversation"
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        session = ChatSession(
            id=session_id or str(uuid.uuid4()),
            title=clean_title,
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.to_dict(include_messages=True)


def list_chat_sessions(limit: int = 30) -> List[Dict[str, Any]]:
    """Returns recent chat sessions ordered by most recently updated."""
    with SessionLocal() as db:
        sessions = (
            db.query(ChatSession)
            .options(joinedload(ChatSession.messages))
            .order_by(desc(ChatSession.updated_at))
            .limit(limit)
            .all()
        )
        return [s.to_dict(include_messages=False) for s in sessions]


def get_chat_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a chat session with ordered messages and live approval statuses."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        session = (
            db.query(ChatSession)
            .options(joinedload(ChatSession.messages))
            .filter(ChatSession.id == session_id)
            .first()
        )
        if not session:
            return None

        approval_ids = {m.approval_id for m in session.messages if m.approval_id}
        approval_map: Dict[str, Dict[str, Any]] = {}
        if approval_ids:
            approvals = (
                db.query(ActionApproval)
                .filter(ActionApproval.id.in_(approval_ids))
                .all()
            )
            dirty = False
            for appr in approvals:
                if appr.status == "pending" and _is_expired(appr.expires_at, now):
                    appr.status = "expired"
                    dirty = True
                approval_map[appr.id] = appr.to_dict()
            if dirty:
                db.commit()

        return session.to_dict(include_messages=True, approval_map=approval_map)


def delete_chat_session(session_id: str) -> bool:
    """Deletes a chat session and its messages; returns False if not found."""
    with SessionLocal() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            return False
        db.delete(session)
        db.commit()
        return True


def add_chat_message(
    session_id: str,
    role: str,
    content: str,
    task_id: Optional[str] = None,
    tool_steps: Optional[List[Dict[str, Any]]] = None,
    approval_id: Optional[str] = None,
    mode: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Appends a user or assistant message to a chat session and refreshes session title/timestamp."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            return None

        if role == "user" and session.title == "New conversation":
            normalized = " ".join(content.strip().split())
            if normalized:
                session.title = f"{normalized[:77]}..." if len(normalized) > 80 else normalized

        session.updated_at = now
        msg = ChatMessage(
            session_id=session_id,
            task_id=task_id,
            role=role,
            content=content,
            tool_steps_json=json.dumps(tool_steps) if tool_steps else None,
            approval_id=approval_id,
            mode=mode,
            created_at=now,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg.to_dict()


def get_chat_history_messages(session_id: str, limit: int = 16) -> List[Dict[str, Any]]:
    """Returns the latest messages in chronological order for LLM conversation context."""
    with SessionLocal() as db:
        items = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(desc(ChatMessage.id))
            .limit(limit)
            .all()
        )
        return [m.to_dict() for m in reversed(items)]


def find_chat_session_by_task(
    task_id: Optional[str] = None,
    approval_id: Optional[str] = None,
) -> Optional[str]:
    """Resolves the originating chat session ID for a task or approval token, if any."""
    with SessionLocal() as db:
        if task_id:
            msg = (
                db.query(ChatMessage)
                .filter(ChatMessage.task_id == task_id)
                .order_by(desc(ChatMessage.id))
                .first()
            )
            if msg:
                return msg.session_id
        if approval_id:
            msg = (
                db.query(ChatMessage)
                .filter(ChatMessage.approval_id == approval_id)
                .order_by(desc(ChatMessage.id))
                .first()
            )
            if msg:
                return msg.session_id
        return None
