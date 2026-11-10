"""Live end-to-end demonstration test simulating Acts 1 through 7."""

from backend.agent.graph import execute_approved_remediation, run_investigation
from backend.db import get_pending_approvals, init_db
from backend.tools.actions import decide_approval
from backend.tools.docker_tools import get_container_status


def test_live_demo_troubleshooting_flow():
    init_db()

    # Ensure nginx-demo is in stopped state for testing investigation and recovery
    from backend.tools.docker_tools import get_docker_client
    try:
        client = get_docker_client()
        c = client.containers.get("nginx-demo")
        if c.status == "running":
            c.stop(timeout=5)
    except Exception:
        pass

    # Verify nginx-demo is currently stopped
    status_before = get_container_status("nginx-demo")
    assert status_before in ("exited", "stopped", "not_found")

    # Act 4: AI Investigation
    task_id = "test-live-recovery-01"
    result = run_investigation(task_id, "Inspect Docker containers and find stopped services")

    assert result["pending_approval_id"] is not None
    assert result["approval_status"] == "pending"

    report = result["final_report"]
    assert "nginx-demo" in report
    assert "Pending Human Approval" in report

    # Act 5: Human Approval
    pending = get_pending_approvals()
    target_appr = next((p for p in pending if p["target"] == "nginx-demo"), None)
    assert target_appr is not None
    appr_id = target_appr["id"]

    # Approve action
    decision_res = decide_approval(appr_id, "approve")
    assert decision_res["status"] == "approved"

    # Act 6: Remediation & Verification
    recovery_res = execute_approved_remediation(task_id, appr_id)
    assert len(recovery_res["execution_results"]) > 0
    assert recovery_res["execution_results"][0]["success"] is True

    # Post-action verification: container is now running!
    status_after = get_container_status("nginx-demo")
    assert status_after == "running"

    recovery_report = recovery_res["final_report"]
    assert "Verification successful: Container 'nginx-demo' is now running." in recovery_report
