"""Live end-to-end recovery evaluation test simulating failure, authorization, and recovery."""

import pytest
from docker.errors import DockerException

from backend.config import settings
from backend.agent.graph import execute_approved_remediation, run_investigation
from backend.db import get_pending_approvals
from backend.tools.actions import decide_approval
from backend.tools.docker_tools import get_container_status, get_docker_client


def test_live_troubleshooting_flow():
    try:
        client = get_docker_client()
    except (DockerException, RuntimeError):
        pytest.skip("Docker daemon unavailable; skipping live recovery test.")

    probe_name = "sysadmin-test-probe"
    test_container = None
    orig_allowed = settings.ALLOWED_CONTAINERS

    try:
        # Cleanup any previous probe if it exists
        try:
            old = client.containers.get(probe_name)
            old.remove(force=True)
        except Exception:
            pass

        # Create transient test workload container
        test_container = client.containers.run(
            "nginx:alpine",
            name=probe_name,
            detach=True,
        )

        # Stop the probe container to simulate an unexpected outage
        test_container.stop(timeout=5)

        # Verify probe is currently stopped
        status_before = get_container_status(probe_name)
        assert status_before in ("exited", "stopped", "not_found")

        # Allow arbitrary non-system containers
        settings.ALLOWED_CONTAINERS = ["*"]

        # AI Investigation
        task_id = "test-live-recovery-01"
        result = run_investigation(task_id, f"Inspect Docker containers and find stopped services")

        assert result["pending_approval_id"] is not None
        assert result["approval_status"] == "pending"

        report = result["final_report"]
        assert probe_name in report
        assert "Pending Human Approval" in report

        # Human Approval Gate
        pending = get_pending_approvals()
        target_appr = next((p for p in pending if p["target"] == probe_name), None)
        assert target_appr is not None
        appr_id = target_appr["id"]

        # Approve action
        decision_res = decide_approval(appr_id, "approve")
        assert decision_res["status"] == "approved"

        # Remediation & Verification
        recovery_res = execute_approved_remediation(task_id, appr_id)
        assert len(recovery_res["execution_results"]) > 0
        assert recovery_res["execution_results"][0]["success"] is True

        # Post-action verification: container is now running!
        status_after = get_container_status(probe_name)
        assert status_after == "running"

        recovery_report = recovery_res["final_report"]
        assert f"Verification successful: Container '{probe_name}' is now running." in recovery_report

    finally:
        settings.ALLOWED_CONTAINERS = orig_allowed
        # Clean teardown of transient test workload
        if test_container:
            try:
                test_container.remove(force=True)
            except Exception:
                pass
        try:
            client.containers.get(probe_name).remove(force=True)
        except Exception:
            pass
