"""Unit tests for system monitoring and threshold evaluation."""

from backend.tools.system import (
    evaluate_thresholds,
    get_disk_usage,
    get_load_average,
    get_network_info,
    get_system_info,
    get_system_metrics,
    get_uptime,
)


def test_get_system_metrics():
    metrics = get_system_metrics()
    assert "cpu_usage_percent" in metrics
    assert isinstance(metrics["cpu_usage_percent"], float)
    assert 0.0 <= metrics["cpu_usage_percent"] <= 100.0
    assert metrics["memory_total_gb"] > 0
    assert 0.0 <= metrics["memory_usage_percent"] <= 100.0


def test_get_disk_usage():
    disk = get_disk_usage()
    assert "disk_total_gb" in disk
    assert disk["disk_total_gb"] > 0
    assert 0.0 <= disk["disk_usage_percent"] <= 100.0


def test_get_system_info():
    info = get_system_info()
    assert "hostname" in info
    assert len(info["hostname"]) > 0
    assert "os" in info
    assert info["cpu_count_logical"] >= 1


def test_get_uptime():
    uptime = get_uptime()
    assert "uptime_seconds" in uptime
    assert uptime["uptime_seconds"] >= 0
    assert "uptime_human" in uptime
    assert len(uptime["uptime_human"]) > 0


def test_get_network_info():
    net = get_network_info()
    assert "bytes_sent_mb" in net
    assert "bytes_recv_mb" in net
    assert isinstance(net["interfaces"], list)


def test_get_load_average():
    load = get_load_average()
    assert "load_1m" in load
    assert "load_5m" in load
    assert "load_15m" in load


def test_evaluate_thresholds():
    h = evaluate_thresholds(cpu_percent=20.0, memory_percent=40.0, disk_percent=50.0)
    assert h["status"] == "healthy"
    assert len(h["issues"]) == 0

    w = evaluate_thresholds(cpu_percent=75.0, memory_percent=50.0, disk_percent=50.0)
    assert w["status"] == "warning"
    assert any("CPU warning" in i for i in w["issues"])

    c = evaluate_thresholds(cpu_percent=95.0, memory_percent=50.0, disk_percent=50.0)
    assert c["status"] == "critical"
    assert any("CPU critical" in i for i in c["issues"])
