"""Host-aware system monitoring tools using psutil and platform."""

import os
import platform
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import psutil

from backend.config import settings

# If running inside Docker with mounted host filesystems, redirect psutil to host proc
host_proc = settings.HOST_PROC or os.environ.get("HOST_PROC")
if host_proc and os.path.exists(host_proc):
    psutil.PROCFS_PATH = host_proc


def get_system_metrics() -> Dict[str, Any]:
    """Retrieves CPU and Memory utilization."""
    # Sample CPU over a short interval for accurate measurement
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()

    return {
        "cpu_usage_percent": round(cpu_percent, 1),
        "cpu_per_core": [round(c, 1) for c in cpu_per_core],
        "memory_total_gb": round(memory.total / (1024**3), 2),
        "memory_used_gb": round(memory.used / (1024**3), 2),
        "memory_free_gb": round(memory.available / (1024**3), 2),
        "memory_usage_percent": round(memory.percent, 1),
        "swap_total_gb": round(swap.total / (1024**3), 2),
        "swap_used_gb": round(swap.used / (1024**3), 2),
        "swap_usage_percent": round(swap.percent, 1),
    }


def get_disk_usage(path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves disk capacity and available space for the primary partition."""
    target_path = path
    if not target_path:
        # If in container with host root mounted, use /host/root if it exists
        if os.path.exists("/host/root"):
            target_path = "/host/root"
        elif platform.system() == "Windows":
            target_path = "C:\\"
        else:
            target_path = "/"

    usage = psutil.disk_usage(target_path)
    return {
        "path": target_path,
        "disk_total_gb": round(usage.total / (1024**3), 2),
        "disk_used_gb": round(usage.used / (1024**3), 2),
        "disk_free_gb": round(usage.free / (1024**3), 2),
        "disk_usage_percent": round(usage.percent, 1),
    }


def get_system_info() -> Dict[str, Any]:
    """Retrieves OS, hostname, kernel, and processor architecture."""
    return {
        "hostname": platform.node(),
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count_logical": psutil.cpu_count(logical=True) or 1,
        "cpu_count_physical": psutil.cpu_count(logical=False) or 1,
    }


def get_uptime() -> Dict[str, Any]:
    """Retrieves server boot time and formatted uptime."""
    boot_time = psutil.boot_time()
    boot_datetime = datetime.fromtimestamp(boot_time)
    uptime_seconds = time.time() - boot_time
    uptime_delta = timedelta(seconds=int(uptime_seconds))

    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    formatted = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"

    return {
        "boot_time": boot_datetime.isoformat(),
        "uptime_seconds": int(uptime_seconds),
        "uptime_human": formatted,
    }


def get_network_info() -> Dict[str, Any]:
    """Retrieves active network interfaces and traffic counters."""
    net_io = psutil.net_io_counters()
    net_if = psutil.net_if_addrs()

    interfaces: List[str] = list(net_if.keys())
    return {
        "bytes_sent_mb": round(net_io.bytes_sent / (1024**2), 2),
        "bytes_recv_mb": round(net_io.bytes_recv / (1024**2), 2),
        "packets_sent": net_io.packets_sent,
        "packets_recv": net_io.packets_recv,
        "interfaces": interfaces,
    }


def get_load_average() -> Dict[str, Any]:
    """Retrieves 1, 5, and 15 minute system load averages."""
    if hasattr(os, "getloadavg"):
        try:
            load1, load5, load15 = os.getloadavg()
            return {
                "load_1m": round(load1, 2),
                "load_5m": round(load5, 2),
                "load_15m": round(load15, 2),
            }
        except OSError:
            pass

    # Windows fallback: emulate load from current cpu percent
    cpu = psutil.cpu_percent(interval=0.1)
    norm = round(cpu / 100.0 * (psutil.cpu_count(logical=True) or 1), 2)
    return {
        "load_1m": norm,
        "load_5m": norm,
        "load_15m": norm,
    }


def evaluate_thresholds(
    cpu_percent: float, memory_percent: float, disk_percent: float
) -> Dict[str, Any]:
    """Evaluates resource metrics against configured warning and critical thresholds."""
    issues = []
    severity = "healthy"

    checks = [
        ("CPU", cpu_percent, settings.CPU_WARNING_THRESHOLD, settings.CPU_CRITICAL_THRESHOLD),
        ("Memory", memory_percent, settings.MEMORY_WARNING_THRESHOLD, settings.MEMORY_CRITICAL_THRESHOLD),
        ("Disk", disk_percent, settings.DISK_WARNING_THRESHOLD, settings.DISK_CRITICAL_THRESHOLD),
    ]

    for name, val, warn, crit in checks:
        if val >= crit:
            severity = "critical"
            issues.append(f"{name} critical: {val}% >= {crit}%")
        elif val >= warn:
            if severity != "critical":
                severity = "warning"
            issues.append(f"{name} warning: {val}% >= {warn}%")

    return {
        "status": severity,
        "issues": issues,
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "disk_percent": disk_percent,
    }
