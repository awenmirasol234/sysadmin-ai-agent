"""Interactive terminal CLI for running investigations and approving actions locally."""

from backend.agent.chat_agent import run_chat_turn
from backend.agent.graph import execute_approved_remediation
from backend.agent.report import append_rejection_outcome
from backend.db import (
    add_chat_message,
    create_chat_session,
    create_task,
    get_pending_approvals,
    init_db,
    log_event,
    update_task_status,
)
from backend.tools.actions import decide_approval


def print_banner():
    print("=" * 60)
    print(" 🤖 SysAdmin AI Agent — Terminal Interactive Console")
    print("=" * 60)
    print("Type your instruction (e.g. 'Check server health', 'Inspect containers')")
    print("Type 'exit' or 'quit' to terminate, or '/new' for a fresh thread.\n")


def main():
    init_db()
    print_banner()
    session_id = create_chat_session(title="Terminal session")["id"]

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
        if user_input.lower() in ("/new", "new"):
            session_id = create_chat_session(title="Terminal session")["id"]
            print(f"\nAgent > Started new conversation thread ({session_id}).\n")
            continue

        print("\nAgent > Thinking and inspecting host/containers...")
        task = create_task(user_input)
        add_chat_message(session_id, "user", user_input, task_id=task.id)
        result = run_chat_turn(session_id, task.id, user_input)

        tool_steps = result.get("tool_steps") or []
        if tool_steps:
            print("")
            for step in tool_steps:
                print(f"  [tool_call] {step.get('tool')} -> {step.get('result_preview')}")

        report = result.get("reply", "No report generated.")
        print("\n" + report + "\n")

        pending_id = result.get("approval_id")
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
                    dec_res = decide_approval(pending_id, decision)
                    if decision == "approve":
                        print("\nAgent > Executing approved remediation and verifying recovery...")
                        remed_result = execute_approved_remediation(task.id, pending_id)
                        remed_text = remed_result.get("final_report", "")
                        print("\n" + remed_text + "\n")
                        add_chat_message(
                            session_id,
                            "assistant",
                            remed_text or "Approved remediation completed.",
                            task_id=task.id,
                            mode="remediation",
                        )
                    else:
                        # Keep CLI task history consistent with REST API rejections.
                        log_event(task.id, "decision", "User rejected proposed remediation.")
                        updated_report = append_rejection_outcome(
                            report,
                            dec_res.get("action_type", "action"),
                            dec_res.get("target", "target"),
                        )
                        update_task_status(task.id, "completed", updated_report)
                        print("\nAgent > Action was rejected. Server state remains unchanged.\n")
                        add_chat_message(
                            session_id,
                            "assistant",
                            f"Proposed action `{dec_res.get('action_type', 'action')}` on `{dec_res.get('target', 'target')}` was rejected. Server state remains unchanged.",
                            task_id=task.id,
                            mode="remediation",
                        )
                else:
                    print("\nAgent > Action skipped for now. Pending in approval center.\n")


if __name__ == "__main__":
    main()
