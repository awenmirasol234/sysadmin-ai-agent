"""View modules for the SysAdmin AI Operations Desk dashboard."""

from dashboard.views.approvals import render_approvals
from dashboard.views.assistant import render_assistant
from dashboard.views.containers import render_containers
from dashboard.views.history import render_history
from dashboard.views.overview import render_overview
from dashboard.views.settings import render_settings

__all__ = [
    "render_overview",
    "render_containers",
    "render_assistant",
    "render_approvals",
    "render_history",
    "render_settings",
]
