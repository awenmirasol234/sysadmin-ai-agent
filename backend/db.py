"""SQLite database engine, SQLAlchemy models, and audit persistence repository."""

from datetime import datetime, timezone
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
