"""Design tokens, CSS injection, and display formatters for the SysAdmin AI dashboard."""

from datetime import datetime, timezone
from typing import Optional, Tuple
import streamlit as st

PALETTE = {
    "canvas": "#F2F4F7",
    "surface": "#FFFFFF",
    "recessed": "#E8ECEF",
    "ink_primary": "#131920",
    "ink_secondary": "#52606D",
    "border": "#D5DCE3",
    "cobalt": "#1D4ED8",
    "cobalt_hover": "#1E40AF",
    "healthy_fg": "#0F766E",
    "healthy_bg": "#CCFBF1",
    "warning_fg": "#B45309",
    "warning_bg": "#FEF3C7",
    "critical_fg": "#B91C1C",
    "critical_bg": "#FEE2E2",
}

TONE_TOKENS: dict[str, Tuple[str, str, str]] = {
    "healthy": (PALETTE["healthy_fg"], PALETTE["healthy_bg"], "#99F6E4"),
    "warning": (PALETTE["warning_fg"], PALETTE["warning_bg"], "#FDE68A"),
    "critical": (PALETTE["critical_fg"], PALETTE["critical_bg"], "#FECACA"),
    "accent": (PALETTE["cobalt"], "#EFF6FF", "#BFDBFE"),
    "neutral": (PALETTE["ink_secondary"], PALETTE["recessed"], PALETTE["border"]),
}

_STATUS_LABELS = {
    "running": "Running",
    "exited": "Exited",
    "paused": "Paused",
    "restarting": "Restarting",
    "created": "Created",
    "dead": "Dead",
    "waiting_approval": "Waiting approval",
    "pending": "Pending",
    "approved": "Approved",
    "rejected": "Rejected",
    "executed": "Executed",
    "expired": "Expired",
    "completed": "Completed",
    "failed": "Failed",
    "healthy": "Healthy",
    "warning": "Warning",
    "critical": "Critical",
    "open": "Open",
    "resolved": "Resolved",
    "dismissed": "Dismissed",
    "tool_call": "Tool call",
    "decision": "Decision",
    "approval_request": "Approval request",
    "none": "None",
    "unhealthy": "Unhealthy",
    "starting": "Starting",
}


def format_status_label(raw: Optional[str]) -> str:
    """Formats internal identifiers cleanly in sentence case."""
    if not raw:
        return "Unknown"
    cleaned = str(raw).strip().lower()
    return _STATUS_LABELS.get(cleaned, cleaned.replace("_", " ").capitalize())


def severity_tone(value: Optional[str]) -> str:
    """Maps container state, incident severity, or task status to a semantic tone."""
    cleaned = (value or "").strip().lower()
    if cleaned in ("running", "healthy", "completed", "approved", "executed", "resolved"):
        return "healthy"
    if cleaned in ("warning", "waiting_approval", "pending", "restarting", "paused", "starting"):
        return "warning"
    if cleaned in ("critical", "failed", "exited", "dead", "rejected", "expired", "unhealthy", "error", "unreachable"):
        return "critical"
    return "neutral"


def threshold_tone(percent: float, warn: float, crit: float) -> str:
    """Maps a resource utilization percentage to a semantic tone."""
    if percent >= crit:
        return "critical"
    if percent >= warn:
        return "warning"
    return "healthy"


def format_timestamp(iso_str: Optional[str]) -> str:
    """Formats ISO-8601 timestamps cleanly for display without raising on unexpected input."""
    if not iso_str:
        return "Not recorded"
    raw = str(iso_str).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return raw


def get_theme_css() -> str:
    """Returns scoped CSS implementing the Precision Instrument Light token system."""
    return f"""
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {{
    --sa-canvas: {PALETTE["canvas"]};
    --sa-surface: {PALETTE["surface"]};
    --sa-recessed: {PALETTE["recessed"]};
    --sa-ink: {PALETTE["ink_primary"]};
    --sa-ink-muted: {PALETTE["ink_secondary"]};
    --sa-border: {PALETTE["border"]};
    --sa-cobalt: {PALETTE["cobalt"]};
    --sa-cobalt-hover: {PALETTE["cobalt_hover"]};
    --sa-font-display: 'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --sa-font-body: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --sa-font-mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Consolas, monospace;
}}

html, body, [data-testid="stAppViewContainer"] {{
    background-color: var(--sa-canvas);
    color: var(--sa-ink);
    font-family: var(--sa-font-body);
}}

[data-testid="stHeader"] {{
    background-color: var(--sa-canvas);
    border-bottom: 1px solid var(--sa-border);
}}

[data-testid="stMainBlockContainer"] {{
    max-width: 1280px;
    padding-top: 2.75rem;
    padding-bottom: 3rem;
}}

[data-testid="stSidebar"] {{
    background-color: var(--sa-recessed);
    border-right: 1px solid var(--sa-border);
}}

[data-testid="stSidebar"] > div:first-child {{
    padding-top: 1.5rem;
}}

h1, h2, h3, h4, .sa-heading {{
    font-family: var(--sa-font-display);
    color: var(--sa-ink);
    letter-spacing: -0.02em;
}}

code, pre, [data-testid="stCode"] code {{
    font-family: var(--sa-font-mono);
    font-variant-numeric: tabular-nums;
}}

[data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] li {{
    max-width: 72ch;
    line-height: 1.58;
}}

[data-baseweb="tab-list"] {{
    gap: 0.25rem;
    border-bottom: 1px solid var(--sa-border);
    padding-bottom: 0;
    margin-bottom: 1.25rem;
}}

[data-baseweb="tab"] {{
    font-family: var(--sa-font-display);
    font-weight: 500;
    font-size: 0.92rem;
    color: var(--sa-ink-muted);
    padding: 0.55rem 0.9rem;
    border-radius: 0;
}}

[data-baseweb="tab"][aria-selected="true"] {{
    color: var(--sa-cobalt);
    font-weight: 600;
}}

button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible {{
    outline: 2px solid var(--sa-cobalt);
    outline-offset: 2px;
}}

[data-testid="stBaseButton-primary"] {{
    background-color: var(--sa-cobalt);
    border: 1px solid var(--sa-cobalt);
    color: #FFFFFF;
    font-weight: 500;
}}

[data-testid="stBaseButton-primary"]:hover {{
    background-color: var(--sa-cobalt-hover);
    border-color: var(--sa-cobalt-hover);
}}

[data-testid="stBaseButton-secondary"] {{
    background-color: var(--sa-surface);
    border: 1px solid var(--sa-border);
    color: var(--sa-ink);
    font-weight: 500;
}}

[data-testid="stDataFrame"] {{
    border: 1px solid var(--sa-border);
    border-radius: 4px;
    background-color: var(--sa-surface);
}}

.sa-header {{
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1.25rem;
    padding: 0 0 1rem 0;
    margin-bottom: 0.75rem;
    border-bottom: 1px solid var(--sa-border);
}}

.sa-header-title {{
    margin: 0;
    font-family: var(--sa-font-display);
    font-size: 1.65rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    color: var(--sa-ink);
    line-height: 1.15;
}}

.sa-header-sub {{
    margin: 0.25rem 0 0 0;
    font-size: 0.92rem;
    color: var(--sa-ink-muted);
}}

.sa-header-specs {{
    display: flex;
    flex-wrap: wrap;
    gap: 1.25rem;
    align-items: center;
}}

.sa-spec-item {{
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
}}

.sa-spec-label {{
    font-size: 0.75rem;
    color: var(--sa-ink-muted);
}}

.sa-spec-value {{
    font-family: var(--sa-font-mono);
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--sa-ink);
    font-variant-numeric: tabular-nums;
}}

.sa-panel {{
    background-color: var(--sa-surface);
    border: 1px solid var(--sa-border);
    border-radius: 4px;
    padding: 1rem 1.15rem;
    margin-bottom: 0.85rem;
}}

.sa-panel-head {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.75rem;
    padding-bottom: 0.65rem;
    margin-bottom: 0.85rem;
    border-bottom: 1px solid var(--sa-border);
}}

.sa-panel-title {{
    margin: 0;
    font-family: var(--sa-font-display);
    font-size: 1rem;
    font-weight: 600;
    color: var(--sa-ink);
}}

.sa-panel-meta {{
    font-family: var(--sa-font-mono);
    font-size: 0.8rem;
    color: var(--sa-ink-muted);
    font-variant-numeric: tabular-nums;
}}

.sa-meter-row {{
    margin-bottom: 0.9rem;
}}

.sa-meter-row:last-child {{
    margin-bottom: 0;
}}

.sa-meter-label-row {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.75rem;
    margin-bottom: 0.3rem;
}}

.sa-meter-name {{
    font-size: 0.88rem;
    font-weight: 500;
    color: var(--sa-ink);
}}

.sa-meter-detail {{
    font-family: var(--sa-font-mono);
    font-size: 0.82rem;
    color: var(--sa-ink-muted);
    font-variant-numeric: tabular-nums;
}}

.sa-meter-val {{
    font-weight: 600;
    color: var(--sa-ink);
}}

.sa-track {{
    position: relative;
    height: 9px;
    width: 100%;
    background-color: var(--sa-recessed);
    border-radius: 2px;
    overflow: hidden;
}}

.sa-fill {{
    height: 100%;
    border-radius: 2px;
    transition: width 180ms ease-out;
}}

.sa-tick {{
    position: absolute;
    top: 0;
    bottom: 0;
    width: 1px;
    background-color: rgba(19, 25, 32, 0.25);
}}

.sa-cores-wrap {{
    margin-top: 0.55rem;
    padding-top: 0.55rem;
    border-top: 1px dashed var(--sa-border);
}}

.sa-cores-head {{
    display: flex;
    justify-content: space-between;
    font-size: 0.78rem;
    color: var(--sa-ink-muted);
    margin-bottom: 0.35rem;
}}

.sa-sparkbars {{
    display: flex;
    align-items: flex-end;
    gap: 4px;
    height: 28px;
    padding: 3px 4px;
    background-color: var(--sa-canvas);
    border: 1px solid var(--sa-border);
    border-radius: 2px;
}}

.sa-sparkbar-col {{
    flex: 1;
    height: 100%;
    display: flex;
    align-items: flex-end;
    background-color: transparent;
}}

.sa-sparkbar-fill {{
    width: 100%;
    min-height: 2px;
    border-radius: 1px 1px 0 0;
}}

.sa-kv-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.7rem 1rem;
}}

.sa-kv-grid-3 {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.65rem;
}}

.sa-kv-cell {{
    display: flex;
    flex-direction: column;
    gap: 0.12rem;
}}

.sa-kv-key {{
    font-size: 0.76rem;
    color: var(--sa-ink-muted);
}}

.sa-kv-val {{
    font-family: var(--sa-font-mono);
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--sa-ink);
    word-break: break-word;
    font-variant-numeric: tabular-nums;
}}

.sa-chip-list {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-top: 0.45rem;
}}

.sa-chip {{
    display: inline-block;
    font-family: var(--sa-font-mono);
    font-size: 0.75rem;
    color: var(--sa-ink);
    background-color: var(--sa-canvas);
    border: 1px solid var(--sa-border);
    border-radius: 2px;
    padding: 0.12rem 0.45rem;
}}

.sa-pill {{
    display: inline-block;
    font-family: var(--sa-font-body);
    font-size: 0.76rem;
    font-weight: 600;
    line-height: 1.2;
    padding: 0.2rem 0.55rem;
    border-radius: 3px;
    border: 1px solid transparent;
    white-space: nowrap;
}}

.sa-banner {{
    background-color: var(--sa-surface);
    border: 1px solid var(--sa-border);
    border-left-width: 3px;
    border-radius: 3px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.85rem;
}}

.sa-banner-title {{
    font-family: var(--sa-font-display);
    font-size: 0.92rem;
    font-weight: 600;
    color: var(--sa-ink);
    margin: 0 0 0.2rem 0;
}}

.sa-banner-body {{
    font-size: 0.86rem;
    color: var(--sa-ink-muted);
    margin: 0;
    line-height: 1.45;
    max-width: 72ch;
}}

.sa-strip {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    border: 1px solid var(--sa-border);
    background-color: var(--sa-surface);
    border-radius: 4px;
    margin-bottom: 0.9rem;
}}

.sa-strip-cell {{
    padding: 0.65rem 0.9rem;
    border-right: 1px solid var(--sa-border);
}}

.sa-strip-cell:last-child {{
    border-right: none;
}}

.sa-strip-num {{
    font-family: var(--sa-font-mono);
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--sa-ink);
    font-variant-numeric: tabular-nums;
}}

.sa-dossier {{
    background-color: var(--sa-surface);
    border: 1px solid var(--sa-border);
    border-left: 3px solid {PALETTE["warning_fg"]};
    border-radius: 4px;
    padding: 1rem 1.15rem;
    margin-bottom: 0.55rem;
}}

.sa-dossier-head {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.65rem;
}}

.sa-dossier-op {{
    font-family: var(--sa-font-display);
    font-size: 1rem;
    font-weight: 600;
    color: var(--sa-ink);
}}

.sa-rail-panel {{
    background-color: var(--sa-surface);
    border: 1px solid var(--sa-border);
    border-radius: 4px;
    padding: 0.75rem 0.85rem;
    margin-bottom: 0.85rem;
}}

@media (max-width: 820px) {{
    [data-testid="stMainBlockContainer"] {{
        padding-left: 1rem;
        padding-right: 1rem;
    }}
    .sa-strip {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .sa-kv-grid-3 {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
}}

@media (prefers-reduced-motion: reduce) {{
    .sa-fill {{
        transition: none;
    }}
}}
"""


def inject_theme_css() -> None:
    """Injects the dashboard stylesheet into Streamlit's head event container."""
    st.html(f"<style>{get_theme_css()}</style>")
