"""LangChain @tool wrappers exposing host metrics, Docker inspection, and gated actions."""

import json
from typing import Any, Dict, List
from langchain_core.tools import BaseTool, tool

from backend.db import get_all_incidents, log_event
from backend.tools.actions import SecurityError, create_approval_request
from backend.tools.docker_tools import (
    get_container_details,
    get_container_logs,
    list_docker_containers,
)
from backend.tools.system import (
    evaluate_thresholds,
    get_disk_usage,
    get_load_average,
    get_network_info,
    get_system_info,
    get_system_metrics,
    get_uptime,
)


def _serialize_result(payload: Any, max_chars: int = 6000) -> str:
    """Serializes tool output as JSON, bounding oversized payloads for LLM context safety."""
    text = json.dumps(payload, default=str)
    if len(text) <= max_chars:
        return text
    return json.dumps({
        "truncated": True,
        "preview": text[: max_chars - 120],
        "note": "Output truncated to stay within context limits.",
    })


@tool
def inspect_host_metrics() -> str:
    """Collect current host CPU, memory, swap, primary disk utilization, uptime, and threshold evaluation."""
    try:
        metrics = get_system_metrics()
        disk = get_disk_usage()
        uptime = get_uptime()
        thresholds = evaluate_thresholds(
            metrics["cpu_usage_percent"],
            metrics["memory_usage_percent"],
            disk["disk_usage_percent"],
        )
        return _serialize_result({
            "metrics": metrics,
            "disk": disk,
            "uptime": uptime,
            "threshold_eval": thresholds,
        })
    except Exception as exc:
        return _serialize_result({"error": str(exc)})


@tool
def inspect_host_network_and_load() -> str:
    """Collect host platform metadata, 1/5/15m load averages, network byte/packet counters, and interfaces."""
    try:
        return _serialize_result({
            "system_info": get_system_info(),
            "load_average": get_load_average(),
            "network": get_network_info(),
        })
    except Exception as exc:
        return _serialize_result({"error": str(exc)})


@tool
def list_containers(include_stopped: bool = True) -> str:
    """List Docker containers on the host with ID, name, image, status, and state."""
    try:
        containers = list_docker_containers(all=include_stopped)
        return _serialize_result({"count": len(containers), "containers": containers})
    except Exception as exc:
        return _serialize_result({"error": str(exc)})


@tool
def inspect_container(container_name: str) -> str:
    """Inspect detailed Docker metadata for one container including exit code, restart count, health, ports, and runtime error."""
    try:
        return _serialize_result(get_container_details(container_name))
    except Exception as exc:
        return _serialize_result({"error": str(exc)})


@tool
def read_container_logs(container_name: str, tail: int = 50) -> str:
    """Read sanitized stdout/stderr log lines from a Docker container (tail clamped between 1 and 200 lines)."""
    bounded_tail = max(1, min(200, int(tail)))
    try:
        return _serialize_result(get_container_logs(container_name, tail=bounded_tail))
    except Exception as exc:
        return _serialize_result({"error": str(exc)})


@tool
def list_recent_incidents(limit: int = 10) -> str:
    """List recent host or container incidents persisted in the audit database."""
    bounded_limit = max(1, min(50, int(limit)))
    try:
        incidents = get_all_incidents(limit=bounded_limit)
        return _serialize_result({"count": len(incidents), "incidents": incidents})
    except Exception as exc:
        return _serialize_result({"error": str(exc)})


def build_agent_tools(task_id: str, approval_sink: List[Dict[str, Any]]) -> List[BaseTool]:
    """Constructs the toolset bound to an active task ID and single-proposal approval sink."""

    @tool
    def propose_container_action(action_type: str, target: str, reason: str) -> str:
        """Create a human-authorization request for a state-changing container operation.

        Supported action_type values: 'restart_container', 'start_container', 'stop_container'.
        Does not execute immediately; returns a pending approval request for the operator to approve or reject.
        """
        if approval_sink:
            return _serialize_result({
                "error": "An action approval request has already been queued in this turn. Wait for human authorization.",
            })
        try:
            req = create_approval_request(
                action_type=action_type,
                target=target,
                reason=reason,
                task_id=task_id,
            )
            approval_sink.append(req)
            log_event(
                task_id,
                "approval_request",
                f"Proposed {req['action_type']} on '{req['target']}' (token {req['approval_id']}).",
            )
            return _serialize_result(req)
        except SecurityError as exc:
            return _serialize_result({"error": str(exc)})
        except Exception as exc:
            return _serialize_result({"error": f"Unable to create approval request: {exc}"})

    return [
        inspect_host_metrics,
        inspect_host_network_and_load,
        list_containers,
        inspect_container,
        read_container_logs,
        list_recent_incidents,
        propose_container_action,
    ]
