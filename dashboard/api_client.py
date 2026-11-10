"""API client wrapper for communicating with the FastAPI backend."""

import os
from typing import Any, Dict, List, Optional
import requests

BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8000")


class APIClient:
    def __init__(self, base_url: str = BACKEND_API_URL):
        self.base_url = base_url.rstrip("/")

    def get_health(self) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/api/health", timeout=3)
            return r.json() if r.status_code == 200 else {"status": "error"}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    def get_system_metrics(self) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/api/system/metrics", timeout=5)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def get_system_info(self) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/api/system/info", timeout=3)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def get_containers(self) -> List[Dict[str, Any]]:
        try:
            r = requests.get(f"{self.base_url}/api/docker/containers", timeout=5)
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []

    def get_container_logs(self, name: str, tail: int = 100) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/api/docker/containers/{name}/logs?tail={tail}", timeout=5)
            return r.json() if r.status_code == 200 else {"logs": []}
        except Exception as e:
            return {"logs": [], "error": str(e)}

    def submit_chat_task(self, message: str) -> Dict[str, Any]:
        try:
            r = requests.post(f"{self.base_url}/api/agent/chat", json={"message": message}, timeout=5)
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as e:
            return {"error": str(e)}

    def get_task(self, task_id: str) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/api/agent/tasks/{task_id}", timeout=5)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def get_task_events(self, task_id: str) -> List[Dict[str, Any]]:
        try:
            r = requests.get(f"{self.base_url}/api/agent/tasks/{task_id}/events", timeout=5)
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        try:
            r = requests.get(f"{self.base_url}/api/approvals", timeout=3)
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []

    def approve_action(self, approval_id: str) -> Dict[str, Any]:
        try:
            r = requests.post(f"{self.base_url}/api/approvals/{approval_id}/approve", timeout=5)
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as e:
            return {"error": str(e)}

    def reject_action(self, approval_id: str) -> Dict[str, Any]:
        try:
            r = requests.post(f"{self.base_url}/api/approvals/{approval_id}/reject", timeout=5)
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as e:
            return {"error": str(e)}

    def get_incidents(self) -> List[Dict[str, Any]]:
        try:
            r = requests.get(f"{self.base_url}/api/incidents", timeout=5)
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []

    def get_history(self) -> List[Dict[str, Any]]:
        try:
            r = requests.get(f"{self.base_url}/api/history", timeout=5)
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []

    def probe_model(self, provider: str, model: str) -> Dict[str, Any]:
        try:
            r = requests.post(
                f"{self.base_url}/api/model/probe",
                json={"provider": provider, "model": model},
                timeout=10,
            )
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as e:
            return {"error": str(e)}


api = APIClient()
