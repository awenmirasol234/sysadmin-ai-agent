"""Controlled, allowlisted system and container actions with human-in-the-loop authorization."""

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Dict, Optional
import uuid

from docker.errors import DockerException, NotFound

from backend.config import settings
from backend.db import ActionApproval, ActionExecution, SessionLocal
from backend.tools.docker_tools import get_container_status, get_docker_client


class SecurityError(Exception):
    """Raised when an action violates security constraints or allowlists."""
    pass


def validate_target(action_type: str, target: str):
    """Validates that the target is explicitly permitted in the allowlist."""
    clean_target = target.strip().lstrip("/")
    allowed_containers = settings.ALLOWED_CONTAINERS
    if isinstance(allowed_containers, str):
        allowed_containers = [c.strip() for c in allowed_containers.split(",")]

    allowed_services = settings.ALLOWED_SERVICES
    if isinstance(allowed_services, str):
        allowed_services = [s.strip() for s in allowed_services.split(",")]

    if "container" in action_type:
        if clean_target not in allowed_containers:
            raise SecurityError(
                f"Target container '{clean_target}' is NOT in the allowed containers allowlist: {allowed_containers}"
            )
    elif "service" in action_type:
        if clean_target not in allowed_services:
            raise SecurityError(
                f"Target service '{clean_target}' is NOT in the allowed services allowlist: {allowed_services}"
            )
    else:
        raise SecurityError(f"Unsupported action type: '{action_type}'")


def compute_action_hash(action_type: str, target: str) -> str:
    """Computes a SHA-256 fingerprint of the action type and target."""
    payload = f"{action_type.strip().lower()}:{target.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_approval_request(
    action_type: str,
    target: str,
    reason: str,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Registers a pending action approval request in SQLite with an expiration timer."""
    validate_target(action_type, target)
    clean_target = target.strip().lstrip("/")
    arg_hash = compute_action_hash(action_type, clean_target)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.APPROVAL_EXPIRATION_SECONDS)
    approval_id = str(uuid.uuid4())

    with SessionLocal() as db:
        approval = ActionApproval(
            id=approval_id,
            task_id=task_id,
            action_type=action_type,
            target=clean_target,
            arguments_hash=arg_hash,
            reason=reason,
            status="pending",
            created_at=now,
            expires_at=expires_at,
        )
        db.add(approval)
        db.commit()

    return {
        "approval_id": approval_id,
        "action_type": action_type,
        "target": clean_target,
        "reason": reason,
        "status": "pending",
        "expires_in_seconds": settings.APPROVAL_EXPIRATION_SECONDS,
        "expires_at": expires_at.isoformat(),
    }


def decide_approval(approval_id: str, decision: str) -> Dict[str, Any]:
    """Approves or rejects a pending action request."""
    decision_clean = decision.strip().lower()
    if decision_clean not in ("approve", "reject"):
        return {"error": f"Invalid decision '{decision}'. Must be 'approve' or 'reject'."}

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        approval = db.query(ActionApproval).filter(ActionApproval.id == approval_id).first()
        if not approval:
            return {"error": f"Approval request '{approval_id}' not found."}

        if approval.status != "pending":
            return {"error": f"Approval request '{approval_id}' is already {approval.status}."}

        # Check expiration
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            approval.status = "expired"
            db.commit()
            return {"error": f"Approval request '{approval_id}' has expired."}

        approval.status = "approved" if decision_clean == "approve" else "rejected"
        approval.decided_at = now
        db.commit()

        return {
            "approval_id": approval_id,
            "status": approval.status,
            "action_type": approval.action_type,
            "target": approval.target,
        }


def execute_approved_action(approval_id: str) -> Dict[str, Any]:
    """Validates authorization token and executes the approved action, verifying result."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        approval = db.query(ActionApproval).filter(ActionApproval.id == approval_id).first()
        if not approval:
            return {"error": f"Approval '{approval_id}' not found."}

        if approval.status == "executed":
            return {"error": f"Security violation: Approval token '{approval_id}' has already been executed."}

        if approval.status != "approved":
            return {"error": f"Cannot execute: Approval status is '{approval.status}', expected 'approved'."}

        # Check expiration
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            approval.status = "expired"
            db.commit()
            return {"error": "Approval token has expired."}

        # Verify target allowlist again
        try:
            validate_target(approval.action_type, approval.target)
        except SecurityError as se:
            approval.status = "rejected"
            db.commit()
            return {"error": f"Security check failed: {str(se)}"}

        # Verify hash integrity
        expected_hash = compute_action_hash(approval.action_type, approval.target)
        if approval.arguments_hash != expected_hash:
            approval.status = "rejected"
            db.commit()
            return {"error": "Security violation: Action arguments fingerprint does not match approved token."}

        # Perform the operation
        action_type = approval.action_type
        target = approval.target
        success = False
        exec_output = ""
        verification_output = ""

        try:
            client = get_docker_client()
            container = client.containers.get(target)

            if action_type == "restart_container":
                container.restart(timeout=10)
                exec_output = f"Container '{target}' restart signal accepted."
            elif action_type == "start_container":
                container.start()
                exec_output = f"Container '{target}' start signal accepted."
            elif action_type == "stop_container":
                container.stop(timeout=10)
                exec_output = f"Container '{target}' stop signal accepted."
            else:
                raise ValueError(f"Unsupported action: {action_type}")

            # Verify outcome
            current_status = get_container_status(target)
            if action_type in ("restart_container", "start_container"):
                if current_status == "running":
                    success = True
                    verification_output = f"Verification successful: Container '{target}' is now running."
                else:
                    success = False
                    verification_output = f"Verification failed: Expected running, but container '{target}' status is '{current_status}'."
            elif action_type == "stop_container":
                if current_status == "exited":
                    success = True
                    verification_output = f"Verification successful: Container '{target}' is now exited."
                else:
                    success = False
                    verification_output = f"Verification failed: Expected exited, but container '{target}' status is '{current_status}'."

        except NotFound:
            exec_output = f"Container '{target}' not found on host."
            verification_output = "Verification failed: Container does not exist."
            success = False
        except DockerException as de:
            exec_output = f"Docker error executing {action_type}: {str(de)}"
            verification_output = "Verification failed due to Docker error."
            success = False
        except Exception as e:
            exec_output = f"Unexpected error: {str(e)}"
            verification_output = f"Verification failed: {str(e)}"
            success = False

        # Invalidate token by marking as executed
        approval.status = "executed"

        # Record execution
        execution = ActionExecution(
            approval_id=approval_id,
            action_type=action_type,
            target=target,
            result=exec_output,
            success=success,
            verification=verification_output,
            executed_at=now,
        )
        db.add(execution)
        db.commit()

        return {
            "success": success,
            "approval_id": approval_id,
            "action_type": action_type,
            "target": target,
            "result": exec_output,
            "verification": verification_output,
        }
