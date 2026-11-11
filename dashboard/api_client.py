"""API client wrapper for communicating with the FastAPI backend."""

import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import requests

BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8000")


class APIClient:
    """Thin HTTP client wrapping FastAPI backend endpoints with graceful fallbacks."""

    def __init__(self, base_url: str = BACKEND_API_URL):
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str, default: Any = None, timeout: int = 5) -> Any:
        """Performs a GET request, returning ``default`` instead of raising on outages."""
        try:
            r = requests.get(f"{self.base_url}{path}", timeout=timeout)
            return r.json() if r.status_code == 200 else (default if default is not None else {})
        except Exception:
            return default if default is not None else {}

    def _post(self, path: str, json: Optional[Dict] = None, timeout: int = 5) -> Dict[str, Any]:
        """Performs a POST request, normalizing HTTP/connection errors into ``{"error": ...}``."""
        try:
            r = requests.post(f"{self.base_url}{path}", json=json, timeout=timeout)
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as e:
            return {"error": str(e)}

    def _delete(self, path: str, timeout: int = 5) -> Dict[str, Any]:
        """Performs a DELETE request, normalizing HTTP/connection errors into ``{"error": ...}``."""
        try:
            r = requests.delete(f"{self.base_url}{path}", timeout=timeout)
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as e:
            return {"error": str(e)}

    def get_health(self) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/api/health", timeout=3)
            return r.json() if r.status_code == 200 else {"status": "error"}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    def get_system_metrics(self) -> Dict[str, Any]:
        return self._get("/api/system/metrics")

    def get_system_info(self) -> Dict[str, Any]:
        return self._get("/api/system/info", timeout=3)

    def get_containers(self) -> List[Dict[str, Any]]:
        return self._get("/api/docker/containers", default=[])

    def get_container_details(self, name: str) -> Dict[str, Any]:
        safe_name = quote(name, safe="")
        return self._get(f"/api/docker/containers/{safe_name}")

    def get_container_logs(self, name: str, tail: int = 100) -> Dict[str, Any]:
        safe_name = quote(name, safe="")
        return self._get(f"/api/docker/containers/{safe_name}/logs?tail={tail}", default={"logs": []})

    def submit_chat_task(self, message: str) -> Dict[str, Any]:
        return self._post("/api/agent/chat", json={"message": message})

    def list_chat_sessions(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self._get(f"/api/chat/sessions?limit={limit}", default=[])

    def create_chat_session(self, title: str = "New conversation") -> Dict[str, Any]:
        return self._post("/api/chat/sessions", json={"title": title})

    def get_chat_session(self, session_id: str) -> Dict[str, Any]:
        safe_id = quote(session_id, safe="")
        return self._get(f"/api/chat/sessions/{safe_id}", default={})

    def delete_chat_session(self, session_id: str) -> Dict[str, Any]:
        safe_id = quote(session_id, safe="")
        return self._delete(f"/api/chat/sessions/{safe_id}")

    def send_chat_message(self, session_id: str, message: str) -> Dict[str, Any]:
        safe_id = quote(session_id, safe="")
        return self._post(f"/api/chat/sessions/{safe_id}/messages", json={"message": message})

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self._get(f"/api/agent/tasks/{task_id}")

    def get_task_events(self, task_id: str) -> List[Dict[str, Any]]:
        return self._get(f"/api/agent/tasks/{task_id}/events", default=[])

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        return self._get("/api/approvals", default=[], timeout=3)

    def approve_action(self, approval_id: str) -> Dict[str, Any]:
        return self._post(f"/api/approvals/{approval_id}/approve")

    def reject_action(self, approval_id: str) -> Dict[str, Any]:
        return self._post(f"/api/approvals/{approval_id}/reject")

    def get_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._get(f"/api/incidents?limit={limit}", default=[])

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._get(f"/api/history?limit={limit}", default=[])

    def probe_model(
        self,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"provider": provider, "model": model}
        if api_key:
            payload["api_key"] = api_key
        if base_url:
            payload["base_url"] = base_url
        return self._post("/api/model/probe", json=payload, timeout=10)


api = APIClient()
