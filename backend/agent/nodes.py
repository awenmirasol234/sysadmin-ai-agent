"""LangGraph workflow nodes for SysAdmin AI Agent."""

from typing import Any, Dict

from backend.agent.report import format_investigation_report
from backend.agent.state import AgentState
from backend.db import log_event, record_incident, update_task_status
from backend.tools.actions import (
    create_approval_request,
    execute_approved_action,
    validate_target,
)
from backend.tools.docker_tools import (
    get_container_details,
    get_container_logs,
    list_docker_containers,
)
from backend.tools.system import (
    evaluate_thresholds,
    get_disk_usage,
    get_system_metrics,
    get_uptime,
)


def understand_request(state: AgentState) -> Dict[str, Any]:
    """Logs user intent and advances investigation workflow."""
    user_request = state.get("user_request", "Check server health")
    task_id = state.get("task_id", "default-task")

    log_event(task_id, "decision", f"Understood task instruction: '{user_request}'")

    return {
        "iteration": state.get("iteration", 0) + 1,
    }


def plan_investigation(state: AgentState) -> Dict[str, Any]:
    """Selects system and container inspection tools based on request scope."""
    user_request = state.get("user_request", "").lower()
    task_id = state.get("task_id", "default-task")

    plan = []
    if any(k in user_request for k in ["container", "docker", "service", "workload", "daemon"]):
        plan.append("list_docker_containers")
    # Overall server health checks include containers, whereas container-only prompts skip host metrics.
    if any(k in user_request for k in ["health", "server", "cpu", "memory", "ram", "disk", "uptime", "all", "system"]):
        plan.extend(["get_system_metrics", "get_disk_usage", "get_uptime", "list_docker_containers"])

    if not plan:
        plan = ["get_system_metrics", "get_disk_usage", "get_uptime", "list_docker_containers"]

    dedup_plan = list(dict.fromkeys(plan))
    log_event(task_id, "decision", f"Formulated investigation plan: {', '.join(dedup_plan)}")

    return {
        "investigation_plan": dedup_plan,
        "iteration": state.get("iteration", 0) + 1,
    }


def execute_tools(state: AgentState) -> Dict[str, Any]:
    """Executes read-only system monitoring and Docker inspection tools."""
    task_id = state.get("task_id", "default-task")
    observations = list(state.get("observations", []))
    # Fallback runs full inspection if execute_tools is invoked without plan_investigation.
    plan = state.get("investigation_plan") or ["get_system_metrics", "list_docker_containers"]

    if "get_system_metrics" in plan:
        try:
            metrics = get_system_metrics()
            disk = get_disk_usage()
            uptime = get_uptime()
            threshold_eval = evaluate_thresholds(
                metrics["cpu_usage_percent"],
                metrics["memory_usage_percent"],
                disk["disk_usage_percent"],
            )
            observations.append({
                "type": "system_metrics",
                "metrics": metrics,
                "disk": disk,
                "uptime": uptime,
                "threshold_eval": threshold_eval,
            })
            log_event(task_id, "tool_call", "Collected system metrics, disk usage, and server uptime.")
        except Exception as e:
            log_event(task_id, "tool_call", f"Failed to collect system metrics: {str(e)}")

    if "list_docker_containers" in plan:
        try:
            containers = list_docker_containers(all=True)
            obs_docker: Dict[str, Any] = {
                "type": "docker_containers",
                "containers": containers,
                "stopped_containers": [],
                "container_details": {},
                "container_logs": {},
            }

            for c in containers:
                c_name = c["name"]
                if c["status"] != "running":
                    obs_docker["stopped_containers"].append(c_name)
                    # Fetch forensic details and sanitized logs only for non-running containers to bound payloads.
                    details = get_container_details(c_name)
                    logs = get_container_logs(c_name, tail=50)
                    obs_docker["container_details"][c_name] = details
                    obs_docker["container_logs"][c_name] = logs.get("logs", [])

            observations.append(obs_docker)
            log_event(
                task_id,
                "tool_call",
                f"Inspected Docker containers ({len(containers)} total, {len(obs_docker['stopped_containers'])} stopped).",
            )
        except Exception as e:
            log_event(task_id, "tool_call", f"Failed to inspect Docker containers: {str(e)}")

    return {
        "observations": observations,
        "iteration": state.get("iteration", 0) + 1,
    }


def analyze_results(state: AgentState) -> Dict[str, Any]:
    """Analyzes observations to identify incidents and issues."""
    task_id = state.get("task_id", "default-task")
    observations = state.get("observations", [])
    findings = list(state.get("findings", []))

    for obs in observations:
        if obs.get("type") == "system_metrics":
            eval_res = obs.get("threshold_eval", {})
            for issue in eval_res.get("issues", []):
                findings.append({
                    "severity": eval_res.get("status", "warning"),
                    "component": "system",
                    "title": "High Resource Usage Detected",
                    "observation": issue,
                    "possible_cause": "Process load or memory leak.",
                    "recommendation": "Inspect top resource-consuming processes.",
                })
                record_incident(
                    component="system",
                    title="High Resource Usage Detected",
                    description=issue,
                    severity=eval_res.get("status", "warning"),
                    task_id=task_id,
                )

        if obs.get("type") == "docker_containers":
            for c_name in obs.get("stopped_containers", []):
                details = obs.get("container_details", {}).get(c_name, {})
                exit_code = details.get("exit_code", "unknown")
                desc = f"Container '{c_name}' is in exited state with exit code {exit_code}."
                findings.append({
                    "severity": "warning",
                    "component": "docker",
                    "title": f"Container Stopped: {c_name}",
                    "target": c_name,
                    "observation": desc,
                    "possible_cause": f"Container stopped unexpectedly or shut down (exit code: {exit_code}).",
                    "recommendation": f"Restart container '{c_name}' if it should be operational.",
                })
                record_incident(
                    component="docker",
                    title=f"Container Stopped: {c_name}",
                    description=desc,
                    severity="warning",
                    task_id=task_id,
                )

    log_event(task_id, "decision", f"Analysis completed: {len(findings)} finding(s) detected.")
    return {
        "findings": findings,
        "iteration": state.get("iteration", 0) + 1,
    }


def decide_next_step(state: AgentState) -> Dict[str, Any]:
    """Creates a pending human approval request when remediable container issues are found."""
    task_id = state.get("task_id", "default-task")
    findings = state.get("findings", [])
    proposed_actions = list(state.get("proposed_actions", []))
    approval_status = state.get("approval_status")

    if approval_status in ("approved", "rejected"):
        return {"iteration": state.get("iteration", 0) + 1}

    pending_approval_id = None
    for f in findings:
        target = f.get("target")
        if f.get("component") == "docker" and target:
            try:
                validate_target("restart_container", target)
                req = create_approval_request(
                    action_type="restart_container",
                    target=target,
                    reason=f"Container '{target}' was detected in stopped state.",
                    task_id=task_id,
                )
                pending_approval_id = req["approval_id"]
                proposed_actions.append(req)
                log_event(
                    task_id,
                    "approval_request",
                    f"Created pending approval '{pending_approval_id}' to restart '{target}'.",
                )
                # Propose at most one remediation per cycle so each container action is reviewed individually.
                break
            except Exception as e:
                log_event(task_id, "decision", f"Skipped proposing action for {target}: {str(e)}")

    update_task_status(
        task_id,
        "waiting_approval" if pending_approval_id else "running",
    )

    return {
        "proposed_actions": proposed_actions,
        "pending_approval_id": pending_approval_id,
        "approval_status": "pending" if pending_approval_id else None,
        "iteration": state.get("iteration", 0) + 1,
    }


def execute_action(state: AgentState) -> Dict[str, Any]:
    """Executes the approved remediation action and records outcome."""
    task_id = state.get("task_id", "default-task")
    approval_id = state.get("pending_approval_id")
    execution_results = list(state.get("execution_results", []))

    if not approval_id:
        return {"execution_results": execution_results}

    log_event(task_id, "tool_call", f"Executing approved action with token '{approval_id}'.")
    result = execute_approved_action(approval_id)
    execution_results.append(result)

    log_event(
        task_id,
        "decision",
        f"Execution outcome: success={result.get('success', False)}, result={result.get('result', result.get('error'))}",
    )

    return {
        "execution_results": execution_results,
        "iteration": state.get("iteration", 0) + 1,
    }


def generate_report(state: AgentState) -> Dict[str, Any]:
    """Synthesizes observations, findings, and authorization status into a Markdown report."""
    task_id = state.get("task_id", "default-task")
    final_report = format_investigation_report(state)
    # Keep waiting_approval status intact when human authorization is pending so polling UIs pause and prompt.
    final_status = "waiting_approval" if state.get("approval_status") == "pending" else "completed"

    update_task_status(task_id, final_status, final_report)
    log_event(task_id, "decision", "Generated final investigation report.")

    return {
        "final_report": final_report,
        "iteration": state.get("iteration", 0) + 1,
    }
