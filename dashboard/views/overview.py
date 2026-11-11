"""Overview telemetry view for host utilization, network/load, and active incidents."""

from typing import Any, Dict
import pandas as pd
import streamlit as st

from dashboard.api_client import api
from dashboard.components import (
    build_host_specs_grid,
    build_network_load_panel,
    build_notice_banner,
    build_resource_panel,
    render_html,
)
from dashboard.theme import format_status_label, format_timestamp


def render_overview(metrics_bundle: Dict[str, Any], sys_info: Dict[str, Any]) -> None:
    """Renders host metrics, load/network telemetry, hardware info, and open incidents."""
    if not metrics_bundle:
        render_html(
            build_notice_banner(
                "Host telemetry unavailable",
                "Unable to retrieve metrics from the backend API. Confirm sysadmin-backend is running, then select Refresh telemetry.",
                tone="critical",
            )
        )
    else:
        metrics = metrics_bundle.get("metrics", {})
        disk = metrics_bundle.get("disk", {})
        uptime = metrics_bundle.get("uptime", {})
        load_avg = metrics_bundle.get("load_average", {})
        network = metrics_bundle.get("network", {})

        col_primary, col_secondary = st.columns([1.7, 1.15], gap="medium")
        with col_primary:
            render_html(build_resource_panel(metrics, disk, uptime.get("uptime_human", "N/A")))
        with col_secondary:
            render_html(build_network_load_panel(load_avg, network))
            render_html(build_host_specs_grid(sys_info))

    st.subheader("Active incidents")
    incidents = api.get_incidents(limit=10)
    if not incidents:
        render_html(
            build_notice_banner(
                "No open incidents",
                "Host utilization and monitored containers are within configured thresholds. Use Run host health check in the sidebar to run a new scan.",
                tone="healthy",
            )
        )
        return

    rows = [
        {
            "Severity": format_status_label(item.get("severity")),
            "Component": format_status_label(item.get("component")),
            "Title": item.get("title", ""),
            "Status": format_status_label(item.get("status")),
            "Recorded at": format_timestamp(item.get("created_at")),
        }
        for item in incidents
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
