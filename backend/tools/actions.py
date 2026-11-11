"""Controlled, allowlisted container actions with human-in-the-loop authorization."""

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Dict, Optional
import uuid

from docker.errors import DockerException, NotFound

from backend.config import settings
from backend.db import (
    complete_approval_execution,
    create_approval_record,
    decide_approval_record,
    prepare_approval_execution,
)
from backend.tools.docker_tools import get_container_status, get_docker_client

SUPPORTED_CONTAINER_ACTIONS = ("restart_container", "start_container", "stop_container")


class SecurityError(Exception):
    """Raised when an action violates security constraints or allowlists."""
    pass


def validate_target(action_type: str, target: str) -> None:
    """Validates that the action is supported and the container target is permitted.

    Args:
        action_type: Operation name (must be in ``SUPPORTED_CONTAINER_ACTIONS``).
        target: Docker container name (optional leading ``/`` is normalized).

    Raises:
        SecurityError: If the action is unsupported, the target contains unsafe
            characters, belongs to protected system containers, or is outside
            ``ALLOWED_CONTAINERS``.
    """
    if action_type not in SUPPORTED_CONTAINER_ACTIONS:
        raise SecurityError(f"Unsupported action type: '{action_type}'")

    # Docker API container names sometimes include a leading slash.
    clean_target = target.strip().lstrip("/")
    if not clean_target or any(char in clean_target for char in [";", "&", "|", "`", "$", "\n", "\r", " "]):
        raise SecurityError(f"Target name '{clean_target}' contains illegal characters.")

    # Self-protection overrides wildcard allowlists so the agent cannot disrupt itself.
    if clean_target in settings.SYSTEM_PROTECTED_CONTAINERS:
        raise SecurityError(
            f"Target container '{clean_target}' is a protected SysAdmin system component and cannot be modified."
        )

    allowed_containers = settings.parse_comma_separated_list(settings.ALLOWED_CONTAINERS)
    if "*" not in allowed_containers and "all" not in allowed_containers and clean_target not in allowed_containers:
        raise SecurityError(
            f"Target container '{clean_target}' is NOT in the allowed containers allowlist: {allowed_containers}"
        )


def compute_action_hash(action_type: str, target: str) -> str:
    """Computes a SHA-256 fingerprint binding an approval token to normalized arguments."""
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

    create_approval_record(
        approval_id=approval_id,
        task_id=task_id,
        action_type=action_type,
        target=clean_target,
        arguments_hash=arg_hash,
        reason=reason,
        created_at=now,
        expires_at=expires_at,
    )

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

    return decide_approval_record(approval_id, decision_clean, datetime.now(timezone.utc))


def execute_approved_action(approval_id: str) -> Dict[str, Any]:
    """Authorizes, executes, and verifies a single-use approved container action.

    Args:
        approval_id: Pending-turned-approved token UUID.

    Returns:
        Result dictionary with ``success``, ``result``, and ``verification``, or
        ``{"error": ...}`` if pre-execution authorization checks fail.
    """
    now = datetime.now(timezone.utc)
    prepared = prepare_approval_execution(
        approval_id=approval_id,
        now=now,
        validate_fn=validate_target,
        hash_fn=compute_action_hash,
    )
    if "error" in prepared:
        return prepared

    action_type = prepared["action_type"]
    target = prepared["target"]
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

        # Verify the container reached the intended lifecycle state after the Docker API call.
        expected_status = "exited" if action_type == "stop_container" else "running"
        current_status = get_container_status(target)
        success = current_status == expected_status
        if success:
            verification_output = f"Verification successful: Container '{target}' is now {expected_status}."
        else:
            verification_output = (
                f"Verification failed: Expected {expected_status}, "
                f"but container '{target}' status is '{current_status}'."
            )

    except NotFound:
        exec_output = f"Container '{target}' not found on host."
        verification_output = "Verification failed: Container does not exist."
    except DockerException as de:
        exec_output = f"Docker error executing {action_type}: {str(de)}"
        verification_output = "Verification failed due to Docker error."
    except Exception as e:
        exec_output = f"Unexpected error: {str(e)}"
        verification_output = f"Verification failed: {str(e)}"

    complete_approval_execution(
        approval_id=approval_id,
        action_type=action_type,
        target=target,
        result=exec_output,
        success=success,
        verification=verification_output,
        executed_at=datetime.now(timezone.utc),
    )

    return {
        "success": success,
        "approval_id": approval_id,
        "action_type": action_type,
        "target": target,
        "result": exec_output,
        "verification": verification_output,
    }
