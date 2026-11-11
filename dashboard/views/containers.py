"""Docker container inventory, forensic inspector, and sanitized log viewer."""

import pandas as pd
import streamlit as st

from dashboard.api_client import api
from dashboard.components import (
    build_container_inspector_summary,
    build_container_summary_strip,
    build_notice_banner,
    render_html,
)
from dashboard.theme import format_status_label, format_timestamp


def render_containers() -> None:
    """Renders container fleet overview with a split-pane inspector and log viewer."""
    containers = api.get_containers()
    if not containers:
        render_html(
            build_notice_banner(
                "No containers found",
                "No Docker containers were reported by the backend. Verify the Docker daemon is active and /var/run/docker.sock is accessible.",
                tone="warning",
            )
        )
        return

    render_html(build_container_summary_strip(containers))

    col_search, col_state = st.columns([2.2, 1.0], gap="small")
    query = col_search.text_input(
        "Filter containers",
        placeholder="Filter by container name or image",
        label_visibility="collapsed",
        key="container_filter_query",
    ).strip().lower()
    state_filter = col_state.selectbox(
        "Filter by state",
        ["All states", "Running", "Stopped or non-running"],
        label_visibility="collapsed",
        key="container_filter_state",
    )

    filtered = []
    for c in containers:
        status = (c.get("status") or "").lower()
        if state_filter == "Running" and status != "running":
            continue
        if state_filter == "Stopped or non-running" and status == "running":
            continue
        haystack = f"{c.get('name', '')} {c.get('image', '')}".lower()
        if query and query not in haystack:
            continue
        filtered.append(c)

    if not filtered:
        render_html(
            build_notice_banner(
                "No containers match filter",
                "Clear the search query or switch the state filter back to All states.",
                tone="neutral",
            )
        )
        return

    col_inventory, col_inspector = st.columns([1.0, 1.35], gap="large")
    with col_inventory:
        table_rows = [
            {
                "Name": c.get("name", ""),
                "Status": format_status_label(c.get("status")),
                "Image": c.get("image", ""),
                "ID": c.get("id", ""),
                "Created": format_timestamp(c.get("created")),
            }
            for c in filtered
        ]
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        container_names = [c["name"] for c in filtered]
        selected_container = st.selectbox(
            "Inspect container",
            container_names,
            key="selected_container_name",
        )

    with col_inspector:
        details = api.get_container_details(selected_container)
        render_html(build_container_inspector_summary(details))

        head_col, tail_col = st.columns([2.2, 1.0], vertical_alignment="bottom")
        head_col.markdown("#### Container log output")
        tail_lines = tail_col.selectbox(
            "Lines to display",
            [50, 100, 200],
            index=0,
            key="container_log_tail",
        )

        log_res = api.get_container_logs(selected_container, tail=tail_lines)
        if "error" in log_res and not log_res.get("logs"):
            render_html(
                build_notice_banner(
                    "Unable to read logs",
                    str(log_res["error"]),
                    tone="warning",
                )
            )
        else:
            logs = log_res.get("logs", [])
            if logs:
                st.code("\n".join(logs), language="text")
            else:
                render_html(
                    build_notice_banner(
                        "No log output recorded",
                        "This container has emitted no stdout or stderr lines within the requested tail window.",
                        tone="neutral",
                    )
                )
