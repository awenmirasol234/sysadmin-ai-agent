"""LangGraph workflow nodes for SysAdmin AI Agent."""

from datetime import datetime, timezone
from typing import Any, Dict, List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agent.llm import get_chat_model
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.state import AgentState
from backend.db import (
    log_event,
    record_incident,
    update_task_status,
)
from backend.tools.actions import (
    create_approval_request,
    execute_approved_action,
    validate_target,
)
from backend.tools.docker_tools import (
    get_container_details,
    get_container_logs,
    get_container_status,
    list_docker_containers,
)
from backend.tools.system import (
    evaluate_thresholds,
    get_disk_usage,
    get_system_info,
    get_system_metrics,
    get_uptime,
)


def understand_request(state: AgentState) -> Dict[str, Any]:
    """Interprets user intent and initializes investigation context."""
    user_request = state.get("user_request", "Check server health")
    task_id = state.get("task_id", "default-task")

    log_event(task_id, "decision", f"Understood task instruction: '{user_request}'")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_request),
    ]

    return {
        "messages": messages,
        "iteration": state.get("iteration", 0) + 1,
    }


def plan_investigation(state: AgentState) -> Dict[str, Any]:
    """Selects appropriate system and container tools to execute."""
    user_request = state.get("user_request", "").lower()
    task_id = state.get("task_id", "default-task")

    plan = []
    if any(k in user_request for k in ["container", "docker", "service", "nginx", "redis", "postgres"]):
        plan.extend(["list_docker_containers", "inspect_targets"])
    if any(k in user_request for k in ["health", "server", "cpu", "memory", "ram", "disk", "uptime", "all"]):
        plan.extend(["get_system_metrics", "get_disk_usage", "get_uptime", "list_docker_containers"])

    if not plan:
        # Default comprehensive health check
        plan = ["get_system_metrics", "get_disk_usage", "get_uptime", "list_docker_containers"]

    # Deduplicate while preserving order
    dedup_plan = list(dict.fromkeys(plan))
    log_event(task_id, "decision", f"Formulated investigation plan: {', '.join(dedup_plan)}")

    return {"iteration": state.get("iteration", 0) + 1}


def execute_tools(state: AgentState) -> Dict[str, Any]:
    """Executes read-only system monitoring and Docker inspection tools."""
    task_id = state.get("task_id", "default-task")
    observations = list(state.get("observations", []))

    # 1. System Metrics & Thresholds
    try:
        metrics = get_system_metrics()
        disk = get_disk_usage()
        uptime = get_uptime()
        threshold_eval = evaluate_thresholds(
            metrics["cpu_usage_percent"],
            metrics["memory_usage_percent"],
            disk["disk_usage_percent"],
        )
        obs_sys = {
            "type": "system_metrics",
            "metrics": metrics,
            "disk": disk,
            "uptime": uptime,
            "threshold_eval": threshold_eval,
        }
        observations.append(obs_sys)
        log_event(task_id, "tool_call", "Collected system metrics, disk usage, and server uptime.")
    except Exception as e:
        log_event(task_id, "tool_call", f"Failed to collect system metrics: {str(e)}")

    # 2. Docker Containers Inspection
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
            c_status = c["status"]
            if c_status != "running":
                obs_docker["stopped_containers"].append(c_name)
                # Fetch details and logs for stopped container
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
        # Check system threshold issues
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

        # Check stopped containers
        if obs.get("type") == "docker_containers":
            stopped = obs.get("stopped_containers", [])
            for c_name in stopped:
                details = obs.get("container_details", {}).get(c_name, {})
                exit_code = details.get("exit_code", "unknown")
                desc = f"Container '{c_name}' is in exited state with exit code {exit_code}."
                finding = {
                    "severity": "warning",
                    "component": "docker",
                    "title": f"Container Stopped: {c_name}",
                    "target": c_name,
                    "observation": desc,
                    "possible_cause": f"Container stopped unexpectedly or shut down (exit code: {exit_code}).",
                    "recommendation": f"Restart container '{c_name}' if it should be operational.",
                }
                findings.append(finding)
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
    """Decides whether to request human approval for remediation or generate report."""
    task_id = state.get("task_id", "default-task")
    findings = state.get("findings", [])
    proposed_actions = list(state.get("proposed_actions", []))
    approval_status = state.get("approval_status")

    # If action was already approved and executed, or rejected by user, we proceed to report
    if approval_status in ("approved", "rejected"):
        return {"iteration": state.get("iteration", 0) + 1}

    # If we found stopped containers, formulate restart action approval request
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
                break  # Process one action per investigation cycle
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
    """Executes the approved remediation action."""
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
        f"Execution outcome: success={result.get('success', False)}, result={result.get('result')}",
    )

    return {
        "execution_results": execution_results,
        "iteration": state.get("iteration", 0) + 1,
    }


def verify_action(state: AgentState) -> Dict[str, Any]:
    """Verifies that the executed action resolved the target issue."""
    task_id = state.get("task_id", "default-task")
    verification_results = list(state.get("verification_results", []))
    exec_results = state.get("execution_results", [])

    for res in exec_results:
        target = res.get("target")
        if target:
            current_status = get_container_status(target)
            ver = {
                "target": target,
                "current_status": current_status,
                "verified_healthy": current_status == "running",
                "details": f"Post-action inspection: container '{target}' is '{current_status}'.",
            }
            verification_results.append(ver)
            log_event(task_id, "decision", ver["details"])

    return {
        "verification_results": verification_results,
        "iteration": state.get("iteration", 0) + 1,
    }


def generate_report(state: AgentState) -> Dict[str, Any]:
    """Synthesizes all findings, actions, and verification into a structured executive report."""
    task_id = state.get("task_id", "default-task")
    user_request = state.get("user_request", "Server health check")
    findings = state.get("findings", [])
    exec_results = state.get("execution_results", [])
    ver_results = state.get("verification_results", [])
    approval_status = state.get("approval_status")
    observations = state.get("observations", [])

    # Extract high-level summary metrics
    sys_metrics = None
    for obs in observations:
        if obs.get("type") == "system_metrics":
            sys_metrics = obs
            break

    # Build structured markdown report
    lines = [
        "# SysAdmin AI — Investigation Report",
        f"**Task ID:** `{task_id}`  ",
        f"**User Request:** {user_request}  ",
        f"**Timestamp:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        "",
        "---",
        "## 1. System Health Overview",
    ]

    if sys_metrics:
        m = sys_metrics["metrics"]
        d = sys_metrics["disk"]
        u = sys_metrics["uptime"]
        lines.extend([
            f"- **CPU Utilization:** {m['cpu_usage_percent']}%",
            f"- **Memory Usage:** {m['memory_usage_percent']}% ({m['memory_used_gb']} GB / {m['memory_total_gb']} GB)",
            f"- **Disk Usage:** {d['disk_usage_percent']}% ({d['disk_used_gb']} GB / {d['disk_total_gb']} GB)",
            f"- **Server Uptime:** {u['uptime_human']}",
        ])
    else:
        lines.append("- System metrics: Not collected or unavailable.")

    lines.extend(["", "## 2. Findings & Incidents"])
    if not findings:
        lines.append("✅ **All inspected components are healthy.** No issues detected.")
    else:
        for idx, f in enumerate(findings, 1):
            lines.extend([
                f"### Finding {idx}: {f['title']}",
                f"- **Severity:** `{f['severity'].upper()}`",
                f"- **Observation:** {f['observation']}",
                f"- **Possible Cause:** {f.get('possible_cause', 'Unknown')}",
                f"- **Recommendation:** {f.get('recommendation', 'Inspect further')}",
                "",
            ])

    if exec_results:
        lines.extend(["## 3. Remediation & Verification"])
        for ex in exec_results:
            lines.extend([
                f"- **Action Executed:** `{ex.get('action_type')}` on `{ex.get('target')}`",
                f"- **Execution Result:** {ex.get('result')}",
                f"- **Verification:** {ex.get('verification')}",
                f"- **Status:** {'✅ Successful' if ex.get('success') else '❌ Failed'}",
                "",
            ])
    elif approval_status == "rejected":
        lines.extend([
            "## 3. Action Authorization",
            "⚠️ **Action Rejected by User:** Remediating action was proposed but user denied authorization. The server remains unchanged.",
            "",
        ])
    elif approval_status == "pending":
        lines.extend([
            "## 3. Action Authorization",
            "⏳ **Pending Human Approval:** Proposed remediation is awaiting authorization in the Approval Center.",
            "",
        ])

    final_report = "\n".join(lines)
    update_task_status(task_id, "completed", final_report)
    log_event(task_id, "decision", "Generated final investigation report.")

    return {
        "final_report": final_report,
        "iteration": state.get("iteration", 0) + 1,
    }
