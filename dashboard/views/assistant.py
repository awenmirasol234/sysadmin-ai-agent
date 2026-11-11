"""AI Assistant view with prompt starters and non-blocking @st.fragment task polling."""

from typing import Any, Dict, List
import streamlit as st

from dashboard.api_client import api
from dashboard.components import build_notice_banner, build_task_status_bar, render_html
from dashboard.theme import format_status_label, format_timestamp

_STARTER_PROMPTS = [
    "Run a complete system and container health check.",
    "Inspect all Docker containers, check stopped workloads, and review logs.",
    "Check CPU, memory, and disk thresholds across this host.",
]


def _render_trace_and_report(task_id: str, task: Dict[str, Any], events: List[Dict[str, Any]]) -> None:
    """Renders task status summary, report content, and chronological audit events."""
    status = task.get("status", "unknown")
    render_html(build_task_status_bar(task_id, status, task.get("started_at") or ""))

    if status == "waiting_approval":
        render_html(
            build_notice_banner(
                "Authorization required before remediation",
                "A remediating container action has been queued. Open the Approvals tab to authorize or reject execution.",
                tone="warning",
            )
        )
    elif status == "failed":
        render_html(
            build_notice_banner(
                "Investigation or remediation failed",
                "Review the execution report and event trace below for diagnostic details.",
                tone="critical",
            )
        )

    st.markdown(task.get("final_report") or "Investigation in progress; no final report written yet.")

    with st.expander(f"Investigation steps and event audit ({len(events)})", expanded=(status == "running")):
        if not events:
            st.write("Waiting for initial tool call or agent event.")
        else:
            for ev in events:
                ev_type = format_status_label(ev.get("event_type"))
                created = format_timestamp(ev.get("created_at"))
                st.write(f"- `{ev_type}` ({created}): {ev.get('description')}")


@st.fragment(run_every=2)
def _live_task_monitor(task_id: str) -> None:
    """Polls an active running task without blocking navigation or other tabs."""
    task = api.get_task(task_id)
    events = api.get_task_events(task_id)
    if not task:
        render_html(
            build_notice_banner(
                "Task record unavailable",
                "The backend did not return state for the active task ID.",
                tone="warning",
            )
        )
        return

    status = task.get("status", "running")
    if status != "running":
        # Trigger a single full-app refresh so sidebar warning badges and Approvals tab count update.
        st.rerun(scope="app")
        return

    render_html(
        build_notice_banner(
            "Investigation running",
            "Collecting live host telemetry and Docker container inspection events every 2 seconds.",
            tone="accent",
        )
    )
    _render_trace_and_report(task_id, task, events)


def render_assistant() -> None:
    """Renders the diagnostic prompt bar, starter tasks, and active investigation view."""
    starter_cols = st.columns(len(_STARTER_PROMPTS), gap="small")
    for idx, prompt_text in enumerate(_STARTER_PROMPTS):
        short_label = prompt_text.rstrip(".").replace("Run a complete ", "Run ")
        if starter_cols[idx].button(short_label, key=f"starter_prompt_{idx}", use_container_width=True):
            st.session_state["assistant_prompt_input"] = prompt_text

    with st.form("assistant_prompt_form", clear_on_submit=False):
        col_input, col_submit = st.columns([4.0, 1.15], gap="small")
        user_prompt = col_input.text_input(
            "Diagnostic instruction",
            placeholder="Describe what to inspect or troubleshoot on this server",
            label_visibility="collapsed",
            key="assistant_prompt_input",
        )
        submitted = col_submit.form_submit_button("Run investigation", type="primary", use_container_width=True)

    if submitted:
        cleaned = user_prompt.strip()
        if not cleaned:
            render_html(
                build_notice_banner(
                    "Instruction required",
                    "Enter a diagnostic prompt or select one of the quick task starters above.",
                    tone="warning",
                )
            )
        else:
            res = api.submit_chat_task(cleaned)
            if "task_id" in res:
                st.session_state["active_task_id"] = res["task_id"]
                st.rerun()
            else:
                render_html(
                    build_notice_banner(
                        "Failed to start investigation",
                        str(res.get("error", "Backend did not return a task ID.")),
                        tone="critical",
                    )
                )

    active_task_id = st.session_state.get("active_task_id")
    if not active_task_id:
        render_html(
            build_notice_banner(
                "Ready to investigate",
                "Submit an instruction above or trigger a quick action from the sidebar to start host and container diagnostics.",
                tone="neutral",
            )
        )
        return

    task = api.get_task(active_task_id)
    if not task:
        render_html(
            build_notice_banner(
                "Active task not found",
                f"No record was found for task '{active_task_id}'. Submit a new investigation above.",
                tone="warning",
            )
        )
        return

    if task.get("status") == "running":
        _live_task_monitor(active_task_id)
    else:
        events = api.get_task_events(active_task_id)
        _render_trace_and_report(active_task_id, task, events)
