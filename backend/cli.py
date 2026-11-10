"""Milestone 1: Interactive Terminal CLI for SysAdmin AI Agent."""

import sys
import uuid
from backend.agent.graph import execute_approved_remediation, run_investigation
from backend.db import create_task, get_pending_approvals, init_db
from backend.tools.actions import decide_approval


def print_banner():
    print("=" * 60)
    print(" 🤖 SysAdmin AI Agent — Terminal Interactive Console")
    print("=" * 60)
    print("Type your instruction (e.g. 'Check server health', 'Inspect containers')")
    print("Type 'exit' or 'quit' to terminate.\n")


def main():
    init_db()
    print_banner()

    while True:
        try:
            user_input = input("You > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Exiting. Goodbye!")
            break

        print("\nAgent > Investigating server and Docker containers...")
        task = create_task(user_input)
        result = run_investigation(task.id, user_input)

        report = result.get("final_report", "No report generated.")
        print("\n" + report + "\n")

        # Check if there is an approval waiting
        pending_id = result.get("pending_approval_id")
        if pending_id:
            pending_list = get_pending_approvals()
            target_approval = next((p for p in pending_list if p["id"] == pending_id), None)
            if target_approval:
                print("=" * 60)
                print(" ⚠️  HUMAN AUTHORIZATION REQUIRED")
                print("=" * 60)
                print(f"Action: {target_approval['action_type']} on {target_approval['target']}")
                print(f"Reason: {target_approval['reason']}")
                decision = input("Authorise this action? (approve/reject/skip) > ").strip().lower()

                if decision in ("approve", "reject"):
                    decide_approval(pending_id, decision)
                    if decision == "approve":
                        print("\nAgent > Executing approved remediation and verifying recovery...")
                        remed_result = execute_approved_remediation(task.id, pending_id)
                        print("\n" + remed_result.get("final_report", "") + "\n")
                    else:
                        print("\nAgent > Action was rejected. Server state remains unchanged.\n")
                else:
                    print("\nAgent > Action skipped for now. Pending in approval center.\n")


if __name__ == "__main__":
    main()
