"""Pure HTML/SVG telemetry and inspection components for the SysAdmin AI dashboard."""

import html
from typing import Any, Dict, Iterable, List
import streamlit as st

from dashboard.theme import (
    PALETTE,
    TONE_TOKENS,
    format_status_label,
    format_timestamp,
    severity_tone,
    threshold_tone,
)


def _esc(value: Any, fallback: str = "") -> str:
    """Escapes dynamic API strings safely for HTML attribute and text contexts."""
    if value is None:
        return html.escape(fallback, quote=True)
    text = str(value).strip()
    if not text and fallback:
        return html.escape(fallback, quote=True)
    return html.escape(text, quote=True)


def build_status_pill(label: str, tone: str = "neutral") -> str:
    """Returns a styled sentence-case semantic pill badge."""
    fg, bg, border = TONE_TOKENS.get(tone, TONE_TOKENS["neutral"])
    return (
        f'<span class="sa-pill" style="color:{fg};background-color:{bg};border-color:{border};">'
        f"{_esc(label)}</span>"
    )


def build_notice_banner(title: str, body: str, tone: str = "neutral") -> str:
    """Builds a directional callout or calm empty-state banner."""
    fg, _, _ = TONE_TOKENS.get(tone, TONE_TOKENS["neutral"])
    return (
        f'<div class="sa-banner" style="border-left-color:{fg};">'
        f'<p class="sa-banner-title">{_esc(title)}</p>'
        f'<p class="sa-banner-body">{_esc(body)}</p>'
        f"</div>"
    )


def build_host_header(
    sys_info: Dict[str, Any],
    health: Dict[str, Any],
    uptime_text: str,
) -> str:
    """Builds the top architectural header strip summarizing host and engine state."""
    is_healthy = health.get("status") == "healthy"
    hostname = sys_info.get("hostname") or "Unknown host"
    os_name = sys_info.get("os") or "Unknown OS"
    os_rel = sys_info.get("os_release") or ""
    os_display = f"{os_name} {os_rel}".strip()
    provider = health.get("provider") or "Unavailable"
    model = health.get("model") or "Unavailable"
    engine_display = f"{provider} / {model}" if is_healthy else "Disconnected"
    status_pill = build_status_pill("Backend connected" if is_healthy else "Backend unreachable", "healthy" if is_healthy else "critical")

    return (
        '<div class="sa-header">'
        '<div>'
        '<h1 class="sa-header-title">SysAdmin AI</h1>'
        '<p class="sa-header-sub">Host telemetry, container diagnostics, and authorized remediation desk</p>'
        '</div>'
        '<div class="sa-header-specs">'
        f'<div class="sa-spec-item"><span class="sa-spec-label">Host</span><span class="sa-spec-value">{_esc(hostname)}</span></div>'
        f'<div class="sa-spec-item"><span class="sa-spec-label">Platform</span><span class="sa-spec-value">{_esc(os_display)}</span></div>'
        f'<div class="sa-spec-item"><span class="sa-spec-label">Uptime</span><span class="sa-spec-value">{_esc(uptime_text or "Not available")}</span></div>'
        f'<div class="sa-spec-item"><span class="sa-spec-label">Model engine</span><span class="sa-spec-value">{_esc(engine_display)}</span></div>'
        f"<div>{status_pill}</div>"
        "</div>"
        "</div>"
    )


def _meter_row(
    label: str,
    percent: float,
    detail: str,
    warn: float,
    crit: float,
) -> str:
    clamped = max(0.0, min(100.0, float(percent)))
    tone = threshold_tone(clamped, warn, crit)
    fg, _, _ = TONE_TOKENS[tone]
    return (
        '<div class="sa-meter-row">'
        '<div class="sa-meter-label-row">'
        f'<span class="sa-meter-name">{_esc(label)}</span>'
        f'<span class="sa-meter-detail"><span class="sa-meter-val" style="color:{fg};">{clamped:.1f}%</span> ({_esc(detail)})</span>'
        "</div>"
        '<div class="sa-track">'
        f'<div class="sa-fill" style="width:{clamped:.1f}%;background-color:{fg};"></div>'
        f'<div class="sa-tick" style="left:{warn:.0f}%;" title="Warning threshold {warn:.0f}%"></div>'
        f'<div class="sa-tick" style="left:{crit:.0f}%;" title="Critical threshold {crit:.0f}%"></div>'
        "</div>"
        "</div>"
    )


def build_resource_panel(
    metrics: Dict[str, Any],
    disk: Dict[str, Any],
    uptime_human: str,
) -> str:
    """Builds the primary host utilization meter panel with per-core sparkbars."""
    cpu_pct = float(metrics.get("cpu_usage_percent", 0.0))
    mem_pct = float(metrics.get("memory_usage_percent", 0.0))
    swap_pct = float(metrics.get("swap_usage_percent", 0.0))
    disk_pct = float(disk.get("disk_usage_percent", 0.0))

    cpu_cores: List[float] = list(metrics.get("cpu_per_core") or [])
    mem_detail = f"{metrics.get('memory_used_gb', 0)} / {metrics.get('memory_total_gb', 0)} GB used"
    swap_detail = f"{metrics.get('swap_used_gb', 0)} / {metrics.get('swap_total_gb', 0)} GB used"
    disk_path = disk.get("path") or "/"
    disk_detail = f"{disk.get('disk_used_gb', 0)} / {disk.get('disk_total_gb', 0)} GB on {disk_path}"

    rows_html = "".join([
        _meter_row("CPU utilization", cpu_pct, f"{len(cpu_cores) or 1} logical cores", 70.0, 90.0),
        _meter_row("Memory usage", mem_pct, mem_detail, 80.0, 95.0),
        _meter_row("Swap usage", swap_pct, swap_detail, 80.0, 95.0),
        _meter_row("Disk capacity", disk_pct, disk_detail, 80.0, 95.0),
    ])

    cores_html = ""
    if cpu_cores:
        bars = []
        for idx, core_val in enumerate(cpu_cores):
            val = max(0.0, min(100.0, float(core_val)))
            bar_color, _, _ = TONE_TOKENS[threshold_tone(val, 70.0, 90.0)]
            if val < 70.0:
                bar_color = PALETTE["cobalt"]
            bars.append(
                f'<div class="sa-sparkbar-col" title="Core {idx}: {val:.1f}%">'
                f'<div class="sa-sparkbar-fill" style="height:{max(8.0, val):.0f}%;background-color:{bar_color};"></div>'
                "</div>"
            )
        peak = max(float(v) for v in cpu_cores)
        cores_html = (
            '<div class="sa-cores-wrap">'
            '<div class="sa-cores-head">'
            f"<span>Per-core load distribution ({len(cpu_cores)} cores)</span>"
            f'<span class="sa-mono">Peak core: {peak:.1f}%</span>'
            "</div>"
            f'<div class="sa-sparkbars">{"".join(bars)}</div>'
            "</div>"
        )

    return (
        '<div class="sa-panel">'
        '<div class="sa-panel-head">'
        '<h3 class="sa-panel-title">Host resource utilization</h3>'
        f'<span class="sa-panel-meta">Uptime { _esc(uptime_human or "N/A") }</span>'
        "</div>"
        f"{rows_html}"
        f"{cores_html}"
        "</div>"
    )


def build_network_load_panel(load_avg: Dict[str, Any], network: Dict[str, Any]) -> str:
    """Builds the load average and network throughput panel."""
    interfaces = list(network.get("interfaces") or [])
    visible_ifaces = interfaces[:8]
    chips = "".join(f'<span class="sa-chip">{_esc(name)}</span>' for name in visible_ifaces)
    if len(interfaces) > 8:
        chips += f'<span class="sa-chip">+{len(interfaces) - 8} more</span>'
    if not chips:
        chips = '<span class="sa-chip">No active interfaces reported</span>'

    return (
        '<div class="sa-panel">'
        '<div class="sa-panel-head">'
        '<h3 class="sa-panel-title">Load averages and network</h3>'
        '<span class="sa-panel-meta">Host telemetry</span>'
        "</div>"
        '<div class="sa-kv-grid-3" style="margin-bottom:0.85rem;">'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Load 1m</span><span class="sa-kv-val">{_esc(load_avg.get("load_1m", "0.0"))}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Load 5m</span><span class="sa-kv-val">{_esc(load_avg.get("load_5m", "0.0"))}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Load 15m</span><span class="sa-kv-val">{_esc(load_avg.get("load_15m", "0.0"))}</span></div>'
        "</div>"
        '<div class="sa-kv-grid">'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Bytes sent</span><span class="sa-kv-val">{_esc(network.get("bytes_sent_mb", 0))} MB</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Bytes received</span><span class="sa-kv-val">{_esc(network.get("bytes_recv_mb", 0))} MB</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Packets sent</span><span class="sa-kv-val">{_esc(network.get("packets_sent", 0))}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Packets received</span><span class="sa-kv-val">{_esc(network.get("packets_recv", 0))}</span></div>'
        "</div>"
        '<div style="margin-top:0.8rem;padding-top:0.65rem;border-top:1px solid var(--sa-border);">'
        '<span class="sa-kv-key">Network interfaces</span>'
        f'<div class="sa-chip-list">{chips}</div>'
        "</div>"
        "</div>"
    )


def build_host_specs_grid(sys_info: Dict[str, Any]) -> str:
    """Builds the compact host hardware specification panel."""
    logical = sys_info.get("cpu_count_logical", 1)
    physical = sys_info.get("cpu_count_physical", 1)
    arch = sys_info.get("architecture") or "Unknown"
    kernel = sys_info.get("os_release") or "Unknown"
    return (
        '<div class="sa-panel">'
        '<div class="sa-panel-head">'
        '<h3 class="sa-panel-title">Host specifications</h3>'
        f'<span class="sa-panel-meta">{_esc(arch)}</span>'
        "</div>"
        '<div class="sa-kv-grid">'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Hostname</span><span class="sa-kv-val">{_esc(sys_info.get("hostname"), "Unknown")}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Operating system</span><span class="sa-kv-val">{_esc(sys_info.get("os"), "Unknown")}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Kernel release</span><span class="sa-kv-val">{_esc(kernel)}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">CPU cores</span><span class="sa-kv-val">{_esc(logical)} logical / {_esc(physical)} physical</span></div>'
        "</div>"
        "</div>"
    )


def build_container_summary_strip(containers: Iterable[Dict[str, Any]]) -> str:
    """Builds a 4-cell container fleet count strip."""
    items = list(containers)
    total = len(items)
    running = sum(1 for c in items if (c.get("status") or "").lower() == "running")
    stopped = sum(1 for c in items if (c.get("status") or "").lower() in ("exited", "dead", "created"))
    other = total - running - stopped

    return (
        '<div class="sa-strip">'
        f'<div class="sa-strip-cell"><div class="sa-kv-key">Total containers</div><div class="sa-strip-num">{total}</div></div>'
        f'<div class="sa-strip-cell"><div class="sa-kv-key">Running</div><div class="sa-strip-num" style="color:{PALETTE["healthy_fg"]};">{running}</div></div>'
        f'<div class="sa-strip-cell"><div class="sa-kv-key">Stopped or exited</div><div class="sa-strip-num" style="color:{PALETTE["critical_fg"] if stopped else PALETTE["ink_primary"]};">{stopped}</div></div>'
        f'<div class="sa-strip-cell"><div class="sa-kv-key">Paused or restarting</div><div class="sa-strip-num" style="color:{PALETTE["warning_fg"] if other else PALETTE["ink_primary"]};">{other}</div></div>'
        "</div>"
    )


def build_container_inspector_summary(details: Dict[str, Any]) -> str:
    """Builds the container forensic detail grid from `/api/docker/containers/{name}`."""
    if not details or "error" in details and "status" not in details:
        err = (details or {}).get("error", "Container inspection details could not be loaded.")
        return build_notice_banner("Inspector unavailable", str(err), tone="warning")

    status_raw = str(details.get("status", "unknown"))
    health_raw = str(details.get("health", "none"))
    ports_list = details.get("ports") or []
    ports_text = ", ".join(str(p) for p in ports_list) if ports_list else "None exposed"
    daemon_error = str(details.get("error") or "").strip()

    error_block = ""
    if daemon_error:
        error_block = (
            '<div style="margin-top:0.75rem;">'
            + build_notice_banner("Docker runtime error", daemon_error, tone="critical")
            + "</div>"
        )

    return (
        '<div class="sa-panel">'
        '<div class="sa-panel-head">'
        f'<h3 class="sa-panel-title">{_esc(details.get("name"), "Container")}</h3>'
        + build_status_pill(format_status_label(status_raw), severity_tone(status_raw))
        + "</div>"
        '<div class="sa-kv-grid">'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Image</span><span class="sa-kv-val">{_esc(details.get("image"), "Unknown")}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Container ID</span><span class="sa-kv-val">{_esc(details.get("id"), "N/A")}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Health check</span><span class="sa-kv-val">{_esc(format_status_label(health_raw))}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Exit code and restarts</span><span class="sa-kv-val">Exit {_esc(details.get("exit_code", 0))} / {_esc(details.get("restart_count", 0))} restarts</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Ports</span><span class="sa-kv-val">{_esc(ports_text)}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Started at</span><span class="sa-kv-val">{_esc(format_timestamp(details.get("started_at")))}</span></div>'
        "</div>"
        f"{error_block}"
        "</div>"
    )


def build_approval_dossier(approval: Dict[str, Any]) -> str:
    """Builds the authorization review block for a pending container remediation."""
    action_label = format_status_label(approval.get("action_type"))
    target = approval.get("target") or "unknown"
    reason = approval.get("reason") or "No rationale recorded."
    created = format_timestamp(approval.get("created_at"))
    expires = format_timestamp(approval.get("expires_at"))

    return (
        '<div class="sa-dossier">'
        '<div class="sa-dossier-head">'
        f'<span class="sa-dossier-op">{_esc(action_label)} on <span class="sa-mono">{_esc(target)}</span></span>'
        + build_status_pill("Pending authorization", "warning")
        + "</div>"
        '<div class="sa-kv-grid" style="margin-bottom:0.65rem;">'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Target container</span><span class="sa-kv-val">{_esc(target)}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Token ID</span><span class="sa-kv-val">{_esc(approval.get("id"), "N/A")}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Requested at</span><span class="sa-kv-val">{_esc(created)}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Expires at</span><span class="sa-kv-val">{_esc(expires)}</span></div>'
        "</div>"
        '<div class="sa-kv-cell">'
        '<span class="sa-kv-key">Rationale</span>'
        f'<span style="font-size:0.9rem;color:var(--sa-ink);line-height:1.45;">{_esc(reason)}</span>'
        "</div>"
        "</div>"
    )


def build_task_status_bar(task_id: str, status_raw: str, started_at: str = "") -> str:
    """Builds a compact task status header bar with escaped task ID and status pill."""
    meta = f"Task ID: {task_id}"
    if started_at:
        meta = f"{meta} | Started {format_timestamp(started_at)}"
    pill = build_status_pill(format_status_label(status_raw), severity_tone(status_raw))
    return (
        '<div class="sa-panel" style="padding:0.7rem 1rem;margin-bottom:0.7rem;">'
        '<div class="sa-panel-head" style="padding-bottom:0;margin-bottom:0;border-bottom:none;align-items:center;">'
        f'<span class="sa-panel-meta">{_esc(meta)}</span>'
        f"{pill}"
        "</div>"
        "</div>"
    )


def build_backend_config_panel(health: Dict[str, Any], backend_url: str) -> str:
    """Builds the active backend LLM configuration key-value panel."""
    is_healthy = health.get("status") == "healthy"
    active_provider = health.get("provider") or "Unavailable"
    active_model = health.get("model") or "Unavailable"
    api_status = "Connected" if is_healthy else "Unreachable"
    return (
        '<div class="sa-panel">'
        '<div class="sa-panel-head">'
        '<h3 class="sa-panel-title">Active backend configuration</h3>'
        '<span class="sa-panel-meta">Loaded from backend .env on startup</span>'
        "</div>"
        '<div class="sa-kv-grid">'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Configured provider</span><span class="sa-kv-val">{_esc(active_provider)}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Configured model</span><span class="sa-kv-val">{_esc(active_model)}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">Backend API URL</span><span class="sa-kv-val">{_esc(backend_url)}</span></div>'
        f'<div class="sa-kv-cell"><span class="sa-kv-key">API health</span><span class="sa-kv-val">{_esc(api_status)}</span></div>'
        "</div>"
        "</div>"
    )


def build_sidebar_status(health: Dict[str, Any], pending_count: int) -> str:
    """Builds the sidebar operations status summary block."""
    is_healthy = health.get("status") == "healthy"
    pill = build_status_pill("Connected" if is_healthy else "Disconnected", "healthy" if is_healthy else "critical")
    provider = health.get("provider") or "N/A"
    model = health.get("model") or "N/A"
    pending_pill = build_status_pill(
        f"{pending_count} awaiting review" if pending_count else "Queue clear",
        "warning" if pending_count else "healthy",
    )
    return (
        '<div class="sa-rail-panel">'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.6rem;">'
        '<span class="sa-kv-key">Backend</span>'
        f"{pill}"
        "</div>"
        '<div class="sa-kv-cell" style="margin-bottom:0.45rem;">'
        '<span class="sa-kv-key">Provider</span>'
        f'<span class="sa-kv-val">{_esc(provider)}</span>'
        "</div>"
        '<div class="sa-kv-cell" style="margin-bottom:0.55rem;">'
        '<span class="sa-kv-key">Model</span>'
        f'<span class="sa-kv-val">{_esc(model)}</span>'
        "</div>"
        '<div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.5rem;border-top:1px solid var(--sa-border);">'
        '<span class="sa-kv-key">Approvals</span>'
        f"{pending_pill}"
        "</div>"
        "</div>"
    )


def render_html(markup: str) -> None:
    """Renders pre-escaped HTML markup using Streamlit's HTML component."""
    st.html(markup)
