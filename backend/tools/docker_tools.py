"""Docker container inspection and monitoring tools using Docker SDK for Python."""

import re
from typing import Any, Dict, List, Optional
import docker
from docker.errors import DockerException, NotFound


def get_docker_client():
    """Initializes and returns a Docker client connected to the host daemon."""
    try:
        return docker.from_env(timeout=5)
    except DockerException as e:
        raise RuntimeError(
            f"Unable to connect to Docker daemon at /var/run/docker.sock: {str(e)}"
        )


def sanitize_log_text(text: str) -> str:
    """Removes sensitive credentials, authorization tokens, and secrets from log lines."""
    # Redact standard password/secret assignments
    text = re.sub(
        r"(password|passwd|secret|api[_-]?key|token|auth)=([^\s&;]+)",
        r"\1=[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # Redact Bearer tokens
    text = re.sub(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer [REDACTED]", text)
    return text


def list_docker_containers(all: bool = True) -> List[Dict[str, Any]]:
    """Lists Docker containers on the host with their current status."""
    client = get_docker_client()
    containers = client.containers.list(all=all)

    result = []
    for c in containers:
        # c.name usually has no leading slash in python-docker, but strip just in case
        name = c.name.lstrip("/")
        image_name = c.image.tags[0] if c.image.tags else c.image.id[:12]
        result.append({
            "id": c.short_id,
            "name": name,
            "image": image_name,
            "status": c.status,  # "running", "exited", "paused", "restarting"
            "state": c.attrs.get("State", {}).get("Status", c.status),
            "created": c.attrs.get("Created", ""),
        })
    return result


def get_container_details(container_name: str) -> Dict[str, Any]:
    """Retrieves detailed inspection information for a specific container."""
    client = get_docker_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        return {"error": f"Container '{container_name}' not found."}
    except Exception as e:
        return {"error": str(e)}

    attrs = container.attrs
    state = attrs.get("State", {})
    config = attrs.get("Config", {})
    network_settings = attrs.get("NetworkSettings", {})

    ports = list(network_settings.get("Ports", {}).keys()) if network_settings.get("Ports") else []

    return {
        "id": container.short_id,
        "name": container.name.lstrip("/"),
        "image": config.get("Image", ""),
        "status": container.status,
        "running": state.get("Running", False),
        "paused": state.get("Paused", False),
        "restarting": state.get("Restarting", False),
        "exit_code": state.get("ExitCode", 0),
        "error": state.get("Error", ""),
        "started_at": state.get("StartedAt", ""),
        "finished_at": state.get("FinishedAt", ""),
        "restart_count": attrs.get("RestartCount", 0),
        "ports": ports,
        "health": state.get("Health", {}).get("Status", "none"),
    }


def get_container_stats(container_name: str) -> Dict[str, Any]:
    """Retrieves real-time CPU and Memory utilization of a running container."""
    client = get_docker_client()
    try:
        container = client.containers.get(container_name)
        if container.status != "running":
            return {
                "container": container_name,
                "status": container.status,
                "cpu_percent": 0.0,
                "memory_used_mb": 0.0,
                "memory_limit_mb": 0.0,
                "memory_percent": 0.0,
            }

        stats = container.stats(stream=False)
        # Calculate CPU %
        cpu_percent = 0.0
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        cpu_delta = (
            cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        )
        system_delta = (
            cpu_stats.get("system_cpu_usage", 0)
            - precpu_stats.get("system_cpu_usage", 0)
        )
        online_cpus = cpu_stats.get("online_cpus", len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", [1]) or [1]))

        if system_delta > 0 and cpu_delta > 0:
            cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100.0, 2)

        # Calculate Memory %
        memory_stats = stats.get("memory_stats", {})
        usage = memory_stats.get("usage", 0)
        limit = memory_stats.get("limit", 1)
        used_mb = round(usage / (1024**2), 2)
        limit_mb = round(limit / (1024**2), 2)
        mem_percent = round((usage / limit) * 100.0, 2) if limit > 0 else 0.0

        return {
            "container": container_name,
            "status": "running",
            "cpu_percent": cpu_percent,
            "memory_used_mb": used_mb,
            "memory_limit_mb": limit_mb,
            "memory_percent": mem_percent,
        }
    except NotFound:
        return {"error": f"Container '{container_name}' not found."}
    except Exception as e:
        return {"error": str(e)}


def get_container_logs(container_name: str, tail: int = 100) -> Dict[str, Any]:
    """Retrieves and sanitizes recent stdout/stderr logs from a container."""
    client = get_docker_client()
    try:
        container = client.containers.get(container_name)
        raw_logs = container.logs(tail=tail, stderr=True, stdout=True).decode("utf-8", errors="replace")
        sanitized = sanitize_log_text(raw_logs)
        lines = [l for l in sanitized.splitlines() if l.strip()]
        return {
            "container": container_name,
            "total_lines": len(lines),
            "logs": lines,
        }
    except NotFound:
        return {"error": f"Container '{container_name}' not found."}
    except Exception as e:
        return {"error": str(e)}


def get_container_status(container_name: str) -> str:
    """Returns the single status string of a container e.g. 'running', 'exited', or 'not_found'."""
    client = get_docker_client()
    try:
        container = client.containers.get(container_name)
        return container.status
    except NotFound:
        return "not_found"
    except Exception:
        return "error"
