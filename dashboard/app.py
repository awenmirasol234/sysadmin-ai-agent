"""Streamlit Operations Desk entrypoint for SysAdmin AI Agent."""

import sys
from pathlib import Path
import streamlit as st

# Support both package execution (PYTHONPATH=/app) and direct `streamlit run dashboard/app.py`.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from dashboard.api_client import api
from dashboard.components import (
    build_host_header,
    build_notice_banner,
    build_sidebar_status,
    render_html,
)
from dashboard.theme import inject_theme_css
from dashboard.views import (
    render_approvals,
    render_assistant,
    render_containers,
    render_history,
    render_overview,
    render_settings,
)

st.set_page_config(
    page_title="SysAdmin AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme_css()

health = api.get_health()
pending_approvals = api.get_pending_approvals()
sys_info = api.get_system_info()
metrics_bundle = api.get_system_metrics()

with st.sidebar:
    st.markdown("### SysAdmin AI")
    st.caption("Operations rail")
    render_html(build_sidebar_status(health, len(pending_approvals)))

    st.markdown("#### Quick actions")
    if st.button("Run host health check", key="rail_health_check", use_container_width=True):
        res = api.submit_chat_task("Run a complete system and container health check.")
        if "task_id" in res:
            st.session_state["active_task_id"] = res["task_id"]
            st.rerun()

    if st.button("Inspect all containers", key="rail_inspect_containers", use_container_width=True):
        res = api.submit_chat_task(
            "Investigate all Docker containers, check for stopped containers and inspect logs."
        )
        if "task_id" in res:
            st.session_state["active_task_id"] = res["task_id"]
            st.rerun()

    st.divider()
    if st.button("Refresh telemetry", key="rail_refresh_telemetry", use_container_width=True):
        st.rerun()

uptime_text = (metrics_bundle.get("uptime") or {}).get("uptime_human", "Not available")
render_html(build_host_header(sys_info, health, uptime_text))

if pending_approvals:
    count = len(pending_approvals)
    noun = "action" if count == 1 else "actions"
    render_html(
        build_notice_banner(
            f"{count} remediation {noun} awaiting authorization",
            "Review pending proposals in the Approvals tab before any container changes are executed.",
            tone="warning",
        )
    )

tabs = st.tabs([
    "Overview",
    "Containers",
    "Assistant",
    f"Approvals ({len(pending_approvals)})",
    "History",
    "Settings",
])

with tabs[0]:
    render_overview(metrics_bundle, sys_info)

with tabs[1]:
    render_containers()

with tabs[2]:
    render_assistant()

with tabs[3]:
    render_approvals()

with tabs[4]:
    render_history()

with tabs[5]:
    render_settings(health)
