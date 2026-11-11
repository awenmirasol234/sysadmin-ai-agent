"""Hybrid LangGraph ReAct agent for multi-turn SysAdmin AI conversations."""

import json
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.agent.graph import run_investigation
from backend.agent.llm import get_chat_model
from backend.agent.tools_registry import build_agent_tools
from backend.config import settings
from backend.db import (
    add_chat_message,
    ensure_task,
    get_chat_history_messages,
    init_db,
    log_event,
    update_task_status,
)

MAX_REACT_STEPS = 8

_SYSTEM_PROMPT = """You are SysAdmin AI, an autonomous system administration and Docker diagnostics copilot.

Operating rules:
1. Always ground answers in real tool outputs before reporting system metrics, container states, exit codes, or logs. Never guess or fabricate host values, container names, or log lines.
2. Select only the diagnostic tools needed for the user's question (e.g., metrics, network/load, container list/details/logs, recent incidents).
3. You cannot run arbitrary shell commands or edit files directly. If asked to perform an unsupported host operation, state clearly what is unsupported and what container/inspection capabilities you have.
4. For container remediation ('restart_container', 'start_container', 'stop_container'), call `propose_container_action` only when recovery or state change is warranted. Never claim the container has restarted yet—tell the user human authorization is required via the approval controls.
5. Keep replies clear, concise, and factual in Markdown."""


class ReActChatState(TypedDict):
    """LangGraph state for one multi-step ReAct conversation turn."""

    messages: Annotated[List[BaseMessage], add_messages]
    task_id: str
    session_id: str
    steps_left: int


def _extract_text_content(content: Any) -> str:
    """Normalizes string or multi-block LLM content into plain Markdown text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(p for p in parts if p).strip()
    return str(content or "").strip()


def _summarize_tool_output(raw_output: str, max_chars: int = 360) -> tuple[str, str]:
    """Extracts a compact preview and execution status ('ok' or 'error') from JSON tool output."""
    status = "ok"
    try:
        parsed = json.loads(raw_output)
        if isinstance(parsed, dict) and "error" in parsed:
            status = "error"
    except Exception:
        pass
    compact = " ".join(raw_output.split())
    if len(compact) > max_chars:
        compact = f"{compact[:max_chars - 3]}..."
    return compact, status


def _has_live_llm_config() -> bool:
    """Returns True when the configured LLM provider has a usable credential or endpoint."""
    provider = (settings.LLM_PROVIDER or "").strip().lower()
    raw_key = (settings.get_api_key(provider) or "").strip()
    key = "" if raw_key == "your-api-key-here" else raw_key
    base_url = (settings.LLM_BASE_URL or "").strip()

    if provider in ("anthropic", "claude", "google", "gemini"):
        return bool(key)
    if provider == "openai":
        return bool(key or base_url)
    if provider in ("openai-compatible", "groq", "deepseek", "vllm", "openrouter"):
        return bool(key or base_url)
    return False


def build_react_chat_graph(
    chat_model: BaseChatModel,
    tools: List[BaseTool],
    task_id: str,
    tool_steps_sink: List[Dict[str, Any]],
):
    """Builds and compiles a cyclic LangGraph ReAct workflow (`agent_reason` <-> `execute_tools`)."""
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = chat_model.bind_tools(tools)

    def agent_reason(state: ReActChatState) -> Dict[str, Any]:
        response = llm_with_tools.invoke([SystemMessage(content=_SYSTEM_PROMPT), *state["messages"]])
        tool_calls = getattr(response, "tool_calls", None) or []
        if tool_calls:
            names = ", ".join(tc.get("name", "unknown") for tc in tool_calls)
            log_event(task_id, "decision", f"Planned tool execution: {names}.")
        else:
            log_event(task_id, "decision", "Synthesized final conversational response.")
        return {
            "messages": [response],
            "steps_left": state.get("steps_left", 1) - 1,
        }

    def execute_tools(state: ReActChatState) -> Dict[str, Any]:
        last_msg = state["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", None) or []
        outputs: List[ToolMessage] = []

        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args") or {}
            call_id = tc.get("id") or f"call_{len(tool_steps_sink)}"

            tool_fn = tools_by_name.get(name)
            if not tool_fn:
                raw_out = json.dumps({"error": f"Unknown tool '{name}'."})
            else:
                try:
                    raw_out = str(tool_fn.invoke(args))
                except Exception as exc:
                    raw_out = json.dumps({"error": str(exc)})

            preview, status = _summarize_tool_output(raw_out)
            tool_steps_sink.append({
                "tool": name,
                "args": args,
                "result_preview": preview,
                "status": status,
            })
            log_event(task_id, "tool_call", f"Ran {name}({json.dumps(args)}) -> {status}")
            outputs.append(ToolMessage(content=raw_out, tool_call_id=call_id, name=name))

        return {"messages": outputs}

    def synthesize_limit(state: ReActChatState) -> Dict[str, Any]:
        log_event(task_id, "decision", "Reached tool iteration budget; summarizing collected observations.")
        final_msg = chat_model.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            *state["messages"],
            HumanMessage(content="Summarize your findings so far cleanly without calling additional tools."),
        ])
        return {"messages": [final_msg]}

    def route_after_reason(state: ReActChatState) -> str:
        last_msg = state["messages"][-1]
        if getattr(last_msg, "tool_calls", None):
            return "tools" if state.get("steps_left", 0) > 0 else "finalize"
        return "end"

    workflow = StateGraph(ReActChatState)
    workflow.add_node("agent_reason", agent_reason)
    workflow.add_node("tools", execute_tools)
    workflow.add_node("finalize", synthesize_limit)

    workflow.set_entry_point("agent_reason")
    workflow.add_conditional_edges(
        "agent_reason",
        route_after_reason,
        {
            "tools": "tools",
            "finalize": "finalize",
            "end": END,
        },
    )
    workflow.add_edge("tools", "agent_reason")
    workflow.add_edge("finalize", END)
    return workflow.compile()


def _convert_history_to_messages(history_rows: List[Dict[str, Any]], current_task_id: str) -> List[BaseMessage]:
    """Converts prior persisted session turns into LangChain messages without duplicating current turn."""
    messages: List[BaseMessage] = []
    for row in history_rows:
        if row.get("task_id") == current_task_id:
            continue
        content = (row.get("content") or "").strip()
        if not content:
            continue
        role = row.get("role")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            tools_used = [step.get("tool") for step in (row.get("tool_steps") or []) if step.get("tool")]
            if tools_used:
                content = f"{content}\n\n[Tools run in this turn: {', '.join(tools_used)}]"
            messages.append(AIMessage(content=content))
    return messages


def _run_deterministic_fallback(
    task_id: str,
    user_message: str,
    fallback_reason: str,
) -> Dict[str, Any]:
    """Runs the rule-based investigation graph when live LLM reasoning is unavailable."""
    log_event(task_id, "decision", f"{fallback_reason} Executing deterministic fallback diagnostics.")
    inv_result = run_investigation(task_id, user_message)

    tool_steps: List[Dict[str, Any]] = []
    for obs in inv_result.get("observations", []):
        obs_type = obs.get("type")
        if obs_type == "system_metrics":
            tool_steps.append({
                "tool": "inspect_host_metrics",
                "args": {},
                "result_preview": json.dumps(obs.get("threshold_eval", {})),
                "status": "ok",
            })
        elif obs_type == "docker_containers":
            containers = obs.get("containers", [])
            stopped = obs.get("stopped_containers", [])
            tool_steps.append({
                "tool": "list_containers",
                "args": {"include_stopped": True},
                "result_preview": f"{len(containers)} containers total, {len(stopped)} non-running.",
                "status": "ok",
            })

    approval_id = inv_result.get("pending_approval_id")
    if approval_id:
        for prop in inv_result.get("proposed_actions", []):
            tool_steps.append({
                "tool": "propose_container_action",
                "args": {"action_type": prop.get("action_type"), "target": prop.get("target")},
                "result_preview": f"Created approval {approval_id}",
                "status": "ok",
            })

    return {
        "reply": inv_result.get("final_report") or "Fallback investigation completed.",
        "tool_steps": tool_steps,
        "approval_id": approval_id,
        "mode": "fallback_rule",
    }


def run_chat_turn(
    session_id: str,
    task_id: str,
    user_message: str,
    model_override: Optional[BaseChatModel] = None,
) -> Dict[str, Any]:
    """Executes one agentic chat turn, persisting assistant reply, tool steps, and approval links."""
    init_db()
    ensure_task(task_id, user_message)

    history_rows = get_chat_history_messages(session_id, limit=16)
    prior_messages = _convert_history_to_messages(history_rows, task_id)

    reply_text = ""
    tool_steps: List[Dict[str, Any]] = []
    approval_sink: List[Dict[str, Any]] = []
    approval_id: Optional[str] = None
    mode = "llm_react"

    if model_override is not None or _has_live_llm_config():
        try:
            chat_model = model_override or get_chat_model()
            tools = build_agent_tools(task_id=task_id, approval_sink=approval_sink)
            graph = build_react_chat_graph(chat_model, tools, task_id, tool_steps)
            result = graph.invoke({
                "messages": [*prior_messages, HumanMessage(content=user_message)],
                "task_id": task_id,
                "session_id": session_id,
                "steps_left": MAX_REACT_STEPS,
            })
            last_msg = result["messages"][-1] if result.get("messages") else None
            reply_text = _extract_text_content(getattr(last_msg, "content", ""))
            if not reply_text:
                reply_text = "Completed inspection without additional text output."
            if approval_sink:
                approval_id = approval_sink[0].get("approval_id")
            final_status = "waiting_approval" if approval_id else "completed"
            update_task_status(task_id, final_status, reply_text)
        except Exception as exc:
            fallback = _run_deterministic_fallback(
                task_id,
                user_message,
                f"LLM agent failed ({type(exc).__name__}: {exc}).",
            )
            reply_text = fallback["reply"]
            tool_steps = fallback["tool_steps"]
            approval_id = fallback["approval_id"]
            mode = fallback["mode"]
    else:
        fallback = _run_deterministic_fallback(
            task_id,
            user_message,
            f"No live credential/base URL configured for '{settings.LLM_PROVIDER}'.",
        )
        reply_text = fallback["reply"]
        tool_steps = fallback["tool_steps"]
        approval_id = fallback["approval_id"]
        mode = fallback["mode"]

    add_chat_message(
        session_id=session_id,
        role="assistant",
        content=reply_text,
        task_id=task_id,
        tool_steps=tool_steps,
        approval_id=approval_id,
        mode=mode,
    )

    return {
        "session_id": session_id,
        "task_id": task_id,
        "reply": reply_text,
        "tool_steps": tool_steps,
        "approval_id": approval_id,
        "mode": mode,
    }
