"""Investigation and remediation audit archive view."""

import streamlit as st

from dashboard.api_client import api
from dashboard.components import build_notice_banner, build_task_status_bar, render_html
from dashboard.theme import format_status_label, format_timestamp


def render_history() -> None:
    """Renders searchable task history with audit reports and logged events."""
    history = api.get_history(limit=30)
    if not history:
        render_html(
            build_notice_banner(
                "No investigation history yet",
                "Completed, waiting, and failed investigations are archived here automatically.",
                tone="neutral",
            )
        )
        return

    col_search, col_status = st.columns([2.2, 1.0], gap="small")
    query = col_search.text_input(
        "Filter history",
        placeholder="Search by prompt or report text",
        label_visibility="collapsed",
        key="history_filter_query",
    ).strip().lower()
    status_filter = col_status.selectbox(
        "Filter by status",
        ["All statuses", "Completed", "Waiting approval", "Failed", "Running"],
        label_visibility="collapsed",
        key="history_filter_status",
    )

    filtered = []
    for item in history:
        status_label = format_status_label(item.get("status"))
        if status_filter != "All statuses" and status_label != status_filter:
            continue
        haystack = f"{item.get('user_request', '')} {item.get('final_report', '')}".lower()
        if query and query not in haystack:
            continue
        filtered.append(item)

    if not filtered:
        render_html(
            build_notice_banner(
                "No matching history records",
                "Adjust the search filter or reset status selection to view earlier tasks.",
                tone="neutral",
            )
        )
        return

    for item in filtered:
        raw_status = item.get("status")
        status_label = format_status_label(raw_status)
        started = format_timestamp(item.get("started_at"))
        req_title = item.get("user_request") or "Investigation task"
        header_label = f"{req_title} ({status_label}, {started})"

        with st.expander(header_label):
            render_html(build_task_status_bar(str(item.get("id", "unknown")), str(raw_status or "unknown")))
            st.markdown(item.get("final_report") or "No report recorded.")

            events = item.get("events", [])
            st.markdown("##### Tool calls and events")
            if not events:
                st.write("No events recorded for this task.")
            else:
                for ev in events:
                    ev_label = format_status_label(ev.get("event_type"))
                    st.write(f"- `{ev_label}`: {ev.get('description')}")
