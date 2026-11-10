"""Streamlit Dashboard for SysAdmin AI Agent."""

import time
import pandas as pd
import streamlit as st

from dashboard.api_client import api

st.set_page_config(
    page_title="SysAdmin AI Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #1E222D;
        border-radius: 8px;
        padding: 16px;
        border: 1px solid #2E3440;
    }
    .status-running { color: #A3BE8C; font-weight: bold; }
    .status-exited { color: #BF616A; font-weight: bold; }
    .badge-critical { background-color: #BF616A; color: white; padding: 3px 8px; border-radius: 4px; }
    .badge-warning { background-color: #EBCB8B; color: black; padding: 3px 8px; border-radius: 4px; }
    .badge-healthy { background-color: #A3BE8C; color: black; padding: 3px 8px; border-radius: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar
st.sidebar.title("🤖 SysAdmin AI")
health = api.get_health()
if health.get("status") == "healthy":
    st.sidebar.success(f"Backend Connected ({health.get('provider')}:{health.get('model')})")
else:
    st.sidebar.error("Backend Disconnected")

# Pending Approvals Count in Sidebar
pending_approvals = api.get_pending_approvals()
if pending_approvals:
    st.sidebar.warning(f"⚠️ {len(pending_approvals)} Action(s) Pending Approval!")

st.sidebar.markdown("---")
st.sidebar.markdown("### Quick Tasks")
if st.sidebar.button("Run Full Health Check"):
    res = api.submit_chat_task("Run a complete system and container health check.")
    if "task_id" in res:
        st.session_state["active_task_id"] = res["task_id"]
        st.rerun()

if st.sidebar.button("Investigate Containers"):
    res = api.submit_chat_task("Investigate all Docker containers, check for stopped containers and inspect logs.")
    if "task_id" in res:
        st.session_state["active_task_id"] = res["task_id"]
        st.rerun()

# Main Tabs
tabs = st.tabs([
    "📊 Overview",
    "🐳 Containers",
    "🤖 AI Assistant",
    f"🛡️ Approvals ({len(pending_approvals)})",
    "📜 History",
    "⚙️ Settings",
])

# ========================================================
# TAB 1: OVERVIEW
# ========================================================
with tabs[0]:
    st.subheader("Server Health & Resource Utilization")
    data = api.get_system_metrics()
    sys_info = api.get_system_info()

    if data:
        metrics = data.get("metrics", {})
        disk = data.get("disk", {})
        uptime = data.get("uptime", {})

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("CPU Usage", f"{metrics.get('cpu_usage_percent', 0.0)}%")
        c2.metric(
            "Memory Usage",
            f"{metrics.get('memory_usage_percent', 0.0)}%",
            f"{metrics.get('memory_used_gb', 0)} / {metrics.get('memory_total_gb', 0)} GB",
        )
        c3.metric(
            "Disk Usage",
            f"{disk.get('disk_usage_percent', 0.0)}%",
            f"{disk.get('disk_used_gb', 0)} / {disk.get('disk_total_gb', 0)} GB",
        )
        c4.metric("Server Uptime", uptime.get("uptime_human", "N/A"))

        # Core Info
        st.markdown("#### Host Information")
        col_a, col_b, col_c = st.columns(3)
        col_a.write(f"**Hostname:** `{sys_info.get('hostname', 'unknown')}`")
        col_b.write(f"**OS / Kernel:** `{sys_info.get('os')} {sys_info.get('os_release')}`")
        col_c.write(f"**CPUs:** `{sys_info.get('cpu_count_logical', 1)} Logical`")

    st.markdown("---")
    st.subheader("Active Incidents")
    incidents = api.get_incidents(limit=10)
    if incidents:
        df_inc = pd.DataFrame(incidents)
        st.dataframe(df_inc[["severity", "component", "title", "status", "created_at"]], use_container_width=True)
    else:
        st.info("No active incidents recorded.")

# ========================================================
# TAB 2: CONTAINERS
# ========================================================
with tabs[1]:
    st.subheader("Docker Container Inventory")
    containers = api.get_containers()
    if containers:
        df_c = pd.DataFrame(containers)
        st.dataframe(df_c[["name", "status", "image", "id", "created"]], use_container_width=True)

        st.markdown("---")
        st.subheader("Inspect Container Logs")
        container_names = [c["name"] for c in containers]
        selected_container = st.selectbox("Select container to view logs:", container_names)
        if selected_container:
            log_res = api.get_container_logs(selected_container, tail=50)
            logs = log_res.get("logs", [])
            if logs:
                st.code("\n".join(logs), language="text")
            else:
                st.write("No logs found or container output empty.")
    else:
        st.warning("No containers found or unable to communicate with Docker daemon.")

# ========================================================
# TAB 3: AI ASSISTANT
# ========================================================
with tabs[2]:
    st.subheader("AI System Administrator")

    # Chat submission
    user_prompt = st.text_input("Enter instruction for the AI Agent:", placeholder="e.g. Investigate stopped containers and recommend solutions")
    if st.button("Submit Instruction") and user_prompt:
        res = api.submit_chat_task(user_prompt)
        if "task_id" in res:
            st.session_state["active_task_id"] = res["task_id"]
            st.rerun()

    active_task_id = st.session_state.get("active_task_id")
    if active_task_id:
        st.markdown(f"**Current Task:** `{active_task_id}`")
        task = api.get_task(active_task_id)
        status = task.get("status", "running")

        if status in ("running", "waiting_approval"):
            st.info(f"Status: **{status.upper()}** (Auto-refreshing...)")
            events = api.get_task_events(active_task_id)
            if events:
                st.markdown("#### Live Investigation Trace")
                for e in events:
                    ev_type = e.get("event_type", "").upper()
                    st.write(f"- `[{ev_type}]` {e.get('description')}")
            time.sleep(2)
            st.rerun()
        else:
            st.success("Investigation Completed!")
            st.markdown(task.get("final_report", "No report available."))

            # Show historical events in expander
            with st.expander("Investigation Steps & Event Audit"):
                events = api.get_task_events(active_task_id)
                for e in events:
                    st.write(f"- `[{e.get('event_type').upper()}]` {e.get('description')}")

# ========================================================
# TAB 4: APPROVALS
# ========================================================
with tabs[3]:
    st.subheader("Human Authorization Gate")
    st.write("All system and container state modifications require explicit human authorization before execution.")

    approvals = api.get_pending_approvals()
    if not approvals:
        st.success("✅ No pending approval requests. Server is operating under authorized parameters.")
    else:
        for a in approvals:
            appr_id = a["id"]
            with st.container():
                st.markdown(f"""
                <div class="metric-card">
                    <h4>⚠️ Remediation Proposal: <code>{a['action_type']}</code> on <code>{a['target']}</code></h4>
                    <p><b>Reason:</b> {a.get('reason')}</p>
                    <p><b>Created:</b> {a.get('created_at')} | <b>Expires at:</b> {a.get('expires_at')}</p>
                </div>
                """, unsafe_allow_html=True)

                col_btn1, col_btn2, _ = st.columns([1, 1, 4])
                if col_btn1.button(f"✅ Approve Execution", key=f"appr_{appr_id}"):
                    res = api.approve_action(appr_id)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.success(res["message"])
                        time.sleep(1)
                        st.rerun()

                if col_btn2.button(f"❌ Reject Action", key=f"rej_{appr_id}"):
                    res = api.reject_action(appr_id)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.warning(res["message"])
                        time.sleep(1)
                        st.rerun()
                st.markdown("")

# ========================================================
# TAB 5: HISTORY
# ========================================================
with tabs[4]:
    st.subheader("Activity & Investigation Audit History")
    history = api.get_history(limit=20)
    if history:
        for item in history:
            with st.expander(f"Task: {item.get('user_request')} — [{item.get('status').upper()}] ({item.get('started_at')})"):
                st.markdown(item.get("final_report", "No report."))
                st.markdown("##### Tool Calls & Events")
                for ev in item.get("events", []):
                    st.write(f"- `[{ev.get('event_type')}]` {ev.get('description')}")
    else:
        st.write("No historical tasks recorded yet.")

# ========================================================
# TAB 6: SETTINGS
# ========================================================
with tabs[5]:
    st.subheader("Model Provider & Settings")
    st.write("Inspect active LLM reasoning engine or test connectivity.")

    p_col1, p_col2 = st.columns(2)
    p_col1.write(f"**Configured Provider:** `{health.get('provider', 'N/A')}`")
    p_col2.write(f"**Configured Model:** `{health.get('model', 'N/A')}`")

    st.markdown("#### Test Model Connectivity")
    test_provider = st.selectbox("Provider to test:", ["openai", "anthropic", "google", "ollama", "openai-compatible"])
    test_model = st.text_input("Model identifier:", value="gpt-4o-mini" if test_provider == "openai" else "llama3.1")
    if st.button("Probe Model Connection"):
        with st.spinner("Probing model connection..."):
            probe_res = api.probe_model(test_provider, test_model)
            if probe_res.get("success"):
                st.success(f"Connection Successful! Response: {probe_res.get('response')}")
            else:
                st.error(f"Probe failed: {probe_res.get('error')}")
