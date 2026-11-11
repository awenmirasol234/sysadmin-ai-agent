"""Markdown report formatting helpers for investigation and remediation outcomes."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_SECTION_3_PREFIX = "## 3."


def _format_remediation_section(execution_results: List[Dict[str, Any]]) -> List[str]:
    lines = ["## 3. Remediation & Verification"]
    for ex in execution_results:
        if "error" in ex and "action_type" not in ex:
            lines.extend([
                f"- **Execution Error:** {ex['error']}",
                "- **Status:** ❌ Failed",
                "",
            ])
            continue
        lines.extend([
            f"- **Action Executed:** `{ex.get('action_type')}` on `{ex.get('target')}`",
            f"- **Execution Result:** {ex.get('result')}",
            f"- **Verification:** {ex.get('verification')}",
            f"- **Status:** {'✅ Successful' if ex.get('success') else '❌ Failed'}",
            "",
        ])
    return lines


def format_investigation_report(state: Dict[str, Any]) -> str:
    """Formats system observations, findings, and authorization state into Markdown."""
    task_id = state.get("task_id", "default-task")
    user_request = state.get("user_request", "Server health check")
    findings = state.get("findings", [])
    exec_results = state.get("execution_results", [])
    approval_status = state.get("approval_status")
    observations = state.get("observations", [])

    sys_metrics = next((obs for obs in observations if obs.get("type") == "system_metrics"), None)

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
        lines.extend(_format_remediation_section(exec_results))
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

    return "\n".join(lines)


def _replace_section_3(existing_report: Optional[str], new_section_lines: List[str]) -> str:
    section_text = "\n".join(new_section_lines)
    if not existing_report:
        return section_text

    marker_idx = existing_report.find(_SECTION_3_PREFIX)
    if marker_idx != -1:
        base = existing_report[:marker_idx].rstrip()
        return f"{base}\n\n{section_text}"

    return f"{existing_report.rstrip()}\n\n{section_text}"


def append_remediation_outcome(
    existing_report: Optional[str],
    execution_results: List[Dict[str, Any]],
) -> str:
    """Preserves the original investigation report while updating Section 3 with execution results."""
    return _replace_section_3(existing_report, _format_remediation_section(execution_results))


def append_rejection_outcome(
    existing_report: Optional[str],
    action_type: str,
    target: str,
) -> str:
    """Preserves the original investigation report while recording user rejection in Section 3."""
    rejection_lines = [
        "## 3. Action Authorization",
        f"⚠️ **Action Rejected by User:** `{action_type}` on `{target}` was denied authorization. Server state remains unchanged.",
        "",
    ]
    return _replace_section_3(existing_report, rejection_lines)
