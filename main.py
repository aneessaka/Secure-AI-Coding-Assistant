"""
main.py
-------
LangGraph-based orchestration for the Secure AI Coding Assistant.
Implements a state machine pipeline that coordinates three agents:
1. Builder (generates code)
2. Hacker (attacks code)
3. Auditor (approves/rejects with remediation)

Supports iteration: if code fails, cycles back to Builder with remediation.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Any, Dict, Optional

# Configure paths
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from dotenv import load_dotenv

# Load environment FIRST
load_dotenv()

from agents.agent_definitions import (
    create_builder_agent,
    create_hacker_agent,
    create_auditor_agent,
    create_build_task,
    create_attack_task,
    create_audit_task,
)
from output.report_writer import save_session_report
from config.settings import get_llm


def _parse_verdict_status(verdict_text: str, iteration: int = 1) -> str:
    """
    Parse the Auditor's verdict text to extract status.
    Returns: "approved" | "rejected" | "escalated"

    Logic:
    - "approved" = code passed review
    - "rejected" = code has issues (on iteration < 3, retry is possible)
    - "escalated" = code has issues on final iteration (no retry possible)
    """
    text_lower = verdict_text.lower()

    if "approved" in text_lower:
        return "approved"
    elif "rejected" in text_lower or "escalated" in text_lower:
        # If on final iteration, return escalated; otherwise rejected
        if iteration >= 3:
            return "escalated"
        else:
            return "rejected"
    else:
        # Default: if no clear verdict, assume rejected for safety
        return "rejected"


def run_pipeline(
    user_request: str,
    language: str = "python",
    max_iterations: int = 3,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Execute the full security review pipeline.

    Args:
        user_request: The user's code generation request
        language: Target programming language (python, rust, etc)
        max_iterations: Maximum iterations before giving up (default 3)
        verbose: Print detailed output

    Returns:
        Pipeline result dict with: {
            "final_verdict": "APPROVED" | "ESCALATED",
            "iterations": int,
            "builder_output": str,
            "hacker_report": str,
            "auditor_verdict": str,
            "remediation_brief": str | None,
        }
    """
    from crewai import Crew

    # Get LLM with fallback (prints active model)
    llm = get_llm()

    # Initialize agents
    builder_agent = create_builder_agent(llm)
    hacker_agent = create_hacker_agent(llm)
    auditor_agent = create_auditor_agent(llm)

    print("\n" + "="*70)
    print("[*] SECURE AI CODING ASSISTANT - PIPELINE START")
    print("="*70)
    print(f"[*] Request: {user_request[:100]}...")
    print(f"[*] Language: {language}")
    print(f"[*] Max Iterations: {max_iterations}")
    print()

    builder_output = ""
    hacker_report = ""
    auditor_verdict = ""
    remediation_brief = ""
    final_verdict = "UNKNOWN"
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        print(f"\n" + "-"*70)
        print(f"[*] ITERATION {iteration}/{max_iterations}")
        print("-"*70 + "\n")

        # === STAGE 1: BUILDER ===
        print(f"[{iteration}] [BUILDER] Generating code...")
        build_task = create_build_task(
            agent=builder_agent,
            user_request=user_request,
            language=language,
            iteration=iteration,
            remediation_brief=remediation_brief,
        )

        try:
            # Create minimal crew for builder
            builder_crew = Crew(
                agents=[builder_agent],
                tasks=[build_task],
                verbose=verbose,
            )
            builder_output = builder_crew.kickoff()
            print(f"[+] Builder output received ({len(str(builder_output))} chars)")
            if verbose:
                print("\n--- Builder Output (Preview) ---")
                output_str = str(builder_output)[:500]
                print(output_str)
                print("...")
        except Exception as e:
            print(f"[-] Builder error: {str(e)}")
            builder_output = f"ERROR: {str(e)}"

        # === STAGE 2: HACKER ===
        print(f"\n[{iteration}] [HACKER] Attacking code...")
        attack_task = create_attack_task(
            agent=hacker_agent,
            builder_output=builder_output,
            iteration=iteration,
        )

        try:
            # Create minimal crew for hacker
            hacker_crew = Crew(
                agents=[hacker_agent],
                tasks=[attack_task],
                verbose=verbose,
            )
            hacker_report = hacker_crew.kickoff()
            print(f"[+] Hacker report received ({len(str(hacker_report))} chars)")
            if verbose:
                print("\n--- Hacker Report (Preview) ---")
                report_str = str(hacker_report)[:500]
                print(report_str)
                print("...")
        except Exception as e:
            print(f"[-] Hacker error: {str(e)}")
            hacker_report = f"ERROR: {str(e)}"

        # === STAGE 3: AUDITOR ===
        print(f"\n[{iteration}] [AUDITOR] Issuing verdict...")
        audit_task = create_audit_task(
            agent=auditor_agent,
            builder_output=builder_output,
            hacker_report=hacker_report,
            iteration=iteration,
            language=language,
        )

        try:
            # Create minimal crew for auditor
            auditor_crew = Crew(
                agents=[auditor_agent],
                tasks=[audit_task],
                verbose=verbose,
            )
            auditor_verdict = auditor_crew.kickoff()
            print(f"[+] Auditor verdict received ({len(str(auditor_verdict))} chars)")
            if verbose:
                print("\n--- Auditor Verdict (Preview) ---")
                verdict_str = str(auditor_verdict)[:500]
                print(verdict_str)
                print("...")
        except Exception as e:
            print(f"[-] Auditor error: {str(e)}")
            auditor_verdict = f"ERROR: {str(e)}"

        # Parse verdict
        final_verdict = _parse_verdict_status(auditor_verdict, iteration)
        # Extract remediation if rejected or escalated
        if final_verdict in ("rejected", "escalated"):
            remediation_brief = auditor_verdict  # Use full verdict as remediation context
        else:
            remediation_brief = ""

        # Convert to display format for messages
        display_verdict = final_verdict.upper()
        print(f"\n[*] ITERATION {iteration} VERDICT: {display_verdict}")

        # Check if approved
        if final_verdict == "approved":
            print(f"\n[+] Code APPROVED on iteration {iteration}!")
            break
        elif iteration < max_iterations:
            print(f"\n[*] Code NEEDS REMEDIATION - retrying...")
        else:
            print(f"\n[-] Max iterations reached. Final verdict: {display_verdict}")

    # === WRITE REPORTS ===
    print(f"\n" + "-"*70)
    print("[*] WRITING AUDIT REPORTS")
    print("-"*70 + "\n")

    audit_result = {
        "timestamp": datetime.now().isoformat(),
        "user_request": user_request,
        "language": language,
        "iterations": iteration,
        "final_verdict": final_verdict,
        "builder_output": str(builder_output),
        "hacker_report": str(hacker_report),
        "auditor_verdict": str(auditor_verdict),
        "remediation_brief": remediation_brief,
        "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "iteration_history": [],
    }

    try:
        save_session_report(audit_result, final_verdict)
        print(f"[+] Reports saved to output/")
    except Exception as e:
        print(f"[-] Report writing error: {str(e)}")

    # === FINAL SUMMARY ===
    print(f"\n{'='*70}")
    print("[+] PIPELINE COMPLETE")
    print(f"{'='*70}")
    print(f"Final Verdict: {final_verdict}")
    print(f"Iterations: {iteration}/{max_iterations}")
    print()

    return audit_result


def main():
    parser = argparse.ArgumentParser(
        description="Secure AI Coding Assistant - LangGraph Pipeline"
    )
    parser.add_argument(
        "--request",
        type=str,
        required=True,
        help="The code generation request",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="python",
        choices=["python", "rust", "javascript", "go"],
        help="Target programming language",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Maximum iterations (1-3)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="Verbose output",
    )

    args = parser.parse_args()

    try:
        result = run_pipeline(
            user_request=args.request,
            language=args.language,
            max_iterations=args.iterations,
            verbose=args.verbose,
        )

        # Print final result
        print(f"\n{'='*70}")
        print("[*] FINAL RESULT")
        print(f"{'='*70}")
        print(json.dumps({
            "verdict": result["final_verdict"],
            "iterations": result["iterations"],
        }, indent=2))

        sys.exit(0 if result["final_verdict"] == "APPROVED" else 1)

    except Exception as e:
        print(f"\n[-] Pipeline Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
