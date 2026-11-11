"""Agentic multi-turn conversational assistant workspace view."""

from typing import Any, Dict, List, Optional
import streamlit as st

from dashboard.api_client import api
from dashboard.components import (
    build_approval_dossier,
    build_chat_mode_notice,
    build_notice_banner,
    build_task_status_bar,
    build_tool_steps_summary,
    render_html,
)

_STARTER_PROMPTS = [
    "Run a complete system and container health check.",
    "Inspect all Docker containers, check stopped workloads, and review logs.",
    "Check CPU, memory, and disk thresholds across this host.",
]


def _ensure_active_session_id() -> Optional[str]:
    """Returns the active chat session ID, creating a session if none exists."""
    session_id = st.session_state.get("active_chat_session_id")
    if session_id:
        return session_id
    created = api.create_chat_session()
    if isinstance(created, dict) and "id" in created:
        st.session_state["active_chat_session_id"] = created["id"]
        return created["id"]
    return None


def _submit_chat_turn(prompt_text: str) -> None:
    """Sends a user message into the active chat session and triggers live task polling."""
    clean_text = (prompt_text or "").strip()
    if not clean_text:
        return

    session_id = _ensure_active_session_id()
    if not session_id:
        render_html(
            build_notice_banner(
                "Session error",
                "Could not initialize a chat session on the backend.",
                tone="critical",
            )
        )
        return

    res = api.send_chat_message(session_id, clean_text)
    if "task_id" in res:
        st.session_state["active_task_id"] = res["task_id"]
        st.rerun()
    else:
        render_html(
            build_notice_banner(
                "Dispatch error",
                str(res.get("error", "Backend did not return a task ID.")),
                tone="critical",
            )
        )


@st.fragment(run_every=1.5)
def _render_live_turn_fragment(task_id: str) -> None:
    """Polls an in-flight agent turn without reloading tabs or resetting UI state."""
    task = api.get_task(task_id)
    if not isinstance(task, dict) or "id" not in task:
        return

    status = str(task.get("status") or "unknown").lower()
    if status != "running":
        st.session_state.pop("active_task_id", None)
        st.rerun(scope="app")
        return

    with st.chat_message("assistant"):
        render_html(build_task_status_bar(task_id, status, task.get("started_at") or ""))
        events = api.get_task_events(task_id)
        if events:
            for ev in events[-6:]:
                ev_type = str(ev.get("event_type", "event")).replace("_", " ").capitalize()
                msg = ev.get("message") or ""
                st.markdown(f"- **{ev_type}:** {msg}")
        else:
            st.caption("Executing tools and evaluating host telemetry...")


def _render_message_entry(msg: Dict[str, Any]) -> None:
    """Renders one persisted chat message with optional tool steps and inline approvals."""
    role = msg.get("role") if msg.get("role") in ("user", "assistant") else "assistant"
    with st.chat_message(role):
        if role == "assistant":
            mode_notice = build_chat_mode_notice(msg.get("mode"))
            if mode_notice:
                render_html(mode_notice)

        st.markdown(msg.get("content") or "")

        if role == "assistant":
            tool_steps = msg.get("tool_steps") or []
            if tool_steps:
                with st.expander(f"Agent tool calls ({len(tool_steps)})", expanded=False):
                    render_html(build_tool_steps_summary(tool_steps))

            approval = msg.get("approval")
            if isinstance(approval, dict) and approval.get("status") == "pending":
                appr_id = str(approval.get("id") or "")
                render_html(build_approval_dossier(approval))
                col_auth, col_reject, _ = st.columns([1.2, 1.1, 3.0], gap="small")
                if col_auth.button(
                    "Authorize action",
                    key=f"chat_appr_{appr_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    res = api.approve_action(appr_id)
                    if "error" in res:
                        render_html(build_notice_banner("Authorization error", str(res["error"]), tone="critical"))
                    else:
                        parent_task_id = approval.get("task_id") or msg.get("task_id")
                        if parent_task_id:
                            st.session_state["active_task_id"] = parent_task_id
                        st.rerun()

                if col_reject.button(
                    "Reject action",
                    key=f"chat_rej_{appr_id}",
                    type="secondary",
                    use_container_width=True,
                ):
                    res = api.reject_action(appr_id)
                    if "error" in res:
                        render_html(build_notice_banner("Rejection error", str(res["error"]), tone="critical"))
                    else:
                        st.rerun()


def render_assistant() -> None:
    """Renders thread controls, multi-turn chat stream, inline approvals, and prompt input."""
    sessions: List[Dict[str, Any]] = api.list_chat_sessions() or []
    session_ids = [s["id"] for s in sessions if isinstance(s, dict) and "id" in s]
    active_session_id = st.session_state.get("active_chat_session_id")

    if active_session_id not in session_ids:
        active_session_id = session_ids[0] if session_ids else None
        if active_session_id:
            st.session_state["active_chat_session_id"] = active_session_id
        else:
            st.session_state.pop("active_chat_session_id", None)

    col_select, col_new, col_del = st.columns([3.2, 1.1, 1.0], gap="small")
    if sessions:
        by_id = {s["id"]: s for s in sessions if isinstance(s, dict) and "id" in s}
        selected_id = col_select.selectbox(
            "Conversation",
            options=session_ids,
            index=session_ids.index(active_session_id) if active_session_id in session_ids else 0,
            format_func=lambda sid: (
                f"{by_id[sid].get('title', 'Conversation')} ({by_id[sid].get('message_count', 0)} msgs)"
            ),
            label_visibility="collapsed",
            key="chat_session_selector",
        )
        if selected_id != active_session_id:
            st.session_state["active_chat_session_id"] = selected_id
            st.session_state.pop("active_task_id", None)
            st.rerun()
    else:
        col_select.markdown("**Conversation thread** No saved threads yet")

    if col_new.button("New conversation", key="chat_new_session", use_container_width=True):
        created = api.create_chat_session()
        if isinstance(created, dict) and "id" in created:
            st.session_state["active_chat_session_id"] = created["id"]
            st.session_state.pop("active_task_id", None)
            st.rerun()

    if col_del.button(
        "Delete conversation",
        key="chat_delete_session",
        disabled=not bool(active_session_id),
        use_container_width=True,
    ):
        if active_session_id:
            api.delete_chat_session(active_session_id)
            st.session_state.pop("active_chat_session_id", None)
            st.session_state.pop("active_task_id", None)
            st.rerun()

    session_data = api.get_chat_session(active_session_id) if active_session_id else {}
    messages = session_data.get("messages", []) if isinstance(session_data, dict) else []

    if not messages:
        render_html(
            build_notice_banner(
                "Conversational operations agent",
                "Ask a diagnostic question below or pick a starter prompt. Read-only inspections run autonomously while state changes request inline authorization.",
                tone="neutral",
            )
        )
        starter_cols = st.columns(len(_STARTER_PROMPTS), gap="small")
        for idx, prompt_text in enumerate(_STARTER_PROMPTS):
            short_label = prompt_text.rstrip(".").replace("Run a complete ", "Run ")
            if starter_cols[idx].button(short_label, key=f"starter_prompt_{idx}", use_container_width=True):
                _submit_chat_turn(prompt_text)
    else:
        for msg in messages:
            _render_message_entry(msg)

    active_task_id = st.session_state.get("active_task_id")
    if active_task_id:
        task_snapshot = api.get_task(active_task_id)
        task_status = str(task_snapshot.get("status") or "").lower() if isinstance(task_snapshot, dict) else ""
        if task_status == "running":
            _render_live_turn_fragment(active_task_id)
        else:
            st.session_state.pop("active_task_id", None)

    prompt = st.chat_input(
        "Ask SysAdmin AI about host health, containers, or logs...",
        key="assistant_chat_input",
    )
    if prompt:
        _submit_chat_turn(prompt)
