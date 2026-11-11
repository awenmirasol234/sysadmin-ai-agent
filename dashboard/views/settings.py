"""Model provider runtime summary and connectivity diagnostics view."""

from typing import Any, Dict
import streamlit as st

from dashboard.api_client import api
from dashboard.components import build_backend_config_panel, build_notice_banner, render_html

_PROVIDER_OPTIONS = ["openai", "anthropic", "google", "openai-compatible"]
_DEFAULT_PROBE_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "google": "gemini-2.5-flash",
    "openai-compatible": "gpt-4o-mini",
}


def render_settings(health: Dict[str, Any]) -> None:
    """Displays active backend model settings and interactive connectivity probe controls."""
    render_html(build_backend_config_panel(health, api.base_url))

    st.subheader("Connection diagnostics")
    active_provider = health.get("provider") or "openai"
    default_idx = _PROVIDER_OPTIONS.index(active_provider) if active_provider in _PROVIDER_OPTIONS else 0
    test_provider = st.selectbox(
        "Provider",
        _PROVIDER_OPTIONS,
        index=default_idx,
        key="probe_provider_select",
    )

    with st.form("model_probe_form", clear_on_submit=False):
        col_model, col_url = st.columns(2, gap="small")
        test_model = col_model.text_input(
            "Model identifier",
            value=_DEFAULT_PROBE_MODELS.get(test_provider, "gpt-4o-mini"),
            key=f"probe_model_input_{test_provider}",
        )
        test_base_url = col_url.text_input(
            "Base URL override (optional)",
            placeholder="https://api.deepseek.com/v1 or http://localhost:20128/v1",
            key="probe_base_url_input",
        )
        test_api_key = st.text_input(
            "API key override (optional)",
            type="password",
            placeholder="Leave blank to use the backend's configured key",
            key="probe_api_key_input",
        )
        probe_submitted = st.form_submit_button("Test connection", type="primary")

    if probe_submitted:
        with st.spinner("Testing model connectivity..."):
            probe_res = api.probe_model(
                provider=test_provider,
                model=test_model.strip(),
                api_key=test_api_key.strip() or None,
                base_url=test_base_url.strip() or None,
            )
        if probe_res.get("success"):
            reply = probe_res.get("response", "")
            resolved_model = probe_res.get("model", test_model)
            render_html(
                build_notice_banner(
                    "Connection verified",
                    f"Model '{resolved_model}' responded cleanly: {reply}",
                    tone="healthy",
                )
            )
        else:
            err = probe_res.get("error") or "Model endpoint did not respond cleanly."
            render_html(
                build_notice_banner(
                    "Connection test failed",
                    f"{err} Verify your model identifier, API key, or Base URL override and retry.",
                    tone="critical",
                )
            )
