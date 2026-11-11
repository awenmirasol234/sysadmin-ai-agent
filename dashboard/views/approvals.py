"""Human-in-the-loop authorization gate view for pending container operations."""

import time
import streamlit as st

from dashboard.api_client import api
from dashboard.components import build_approval_dossier, build_notice_banner, render_html


def render_approvals() -> None:
    """Displays pending remediation requests with explicit authorize and reject actions."""
    render_html(
        build_notice_banner(
            "Human authorization policy",
            "State-changing container actions use single-use SHA-256 bound tokens with a 300-second expiration window. Protected core containers remain blocked.",
            tone="neutral",
        )
    )

    approvals = api.get_pending_approvals()
    if not approvals:
        render_html(
            build_notice_banner(
                "No pending authorizations",
                "All proposed actions have been resolved. Any container remediation proposed by an investigation will appear here for review.",
                tone="healthy",
            )
        )
        return

    for item in approvals:
        appr_id = item["id"]
        render_html(build_approval_dossier(item))

        col_auth, col_reject, _ = st.columns([1.2, 1.1, 3.0], gap="small")
        if col_auth.button("Authorize action", key=f"appr_{appr_id}", type="primary", use_container_width=True):
            res = api.approve_action(appr_id)
            if "error" in res:
                render_html(build_notice_banner("Authorization error", str(res["error"]), tone="critical"))
            else:
                render_html(
                    build_notice_banner(
                        "Action authorized",
                        str(res.get("message", "Executing remediation and verifying container state.")),
                        tone="healthy",
                    )
                )
                time.sleep(0.8)
                st.rerun()

        if col_reject.button("Reject action", key=f"rej_{appr_id}", type="secondary", use_container_width=True):
            res = api.reject_action(appr_id)
            if "error" in res:
                render_html(build_notice_banner("Rejection error", str(res["error"]), tone="critical"))
            else:
                render_html(
                    build_notice_banner(
                        "Action rejected",
                        str(res.get("message", "Server state remains unchanged.")),
                        tone="warning",
                    )
                )
                time.sleep(0.8)
                st.rerun()
