"""SQLite database engine, SQLAlchemy models, and audit persistence repository."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
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
    event_type = Column(String(32), nullable=False)  # tool_call, observation, decision, approval
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
    component = Column(String(32), nullable=False)  # docker, system, service
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


# Engine and Session initialization
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Creates all database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Yields a database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Repository Helpers
def create_task(user_request: str) -> AgentTask:
    with SessionLocal() as db:
        task = AgentTask(user_request=user_request, status="running")
        db.add(task)
        db.commit()
        db.refresh(task)
        return task


def update_task_status(task_id: str, status: str, final_report: Optional[str] = None):
    with SessionLocal() as db:
        task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if task:
            task.status = status
            if final_report:
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
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        # Mark expired
        expired = (
            db.query(ActionApproval)
            .filter(ActionApproval.status == "pending", ActionApproval.expires_at < now)
            .all()
        )
        for exp in expired:
            exp.status = "expired"
        if expired:
            db.commit()

        approvals = (
            db.query(ActionApproval)
            .filter(ActionApproval.status == "pending")
            .order_by(desc(ActionApproval.created_at))
            .all()
        )
        return [a.to_dict() for a in approvals]


def get_task_history(limit: int = 20) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        tasks = db.query(AgentTask).order_by(desc(AgentTask.started_at)).limit(limit).all()
        return [t.to_dict() for t in tasks]
