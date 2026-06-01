"""
output/report_writer.py
-----------------------
Saves the complete audit trail for each pipeline session.
Each session produces a structured JSON report and a human-readable
Markdown report for review and compliance records.
"""

import json
from pathlib import Path
from datetime import datetime

# Security utilities for output sanitization
try:
    from security_utils import sanitize_output
except ImportError:
    import re
    def sanitize_output(text: str, redact_secrets: bool = True) -> str:
        if not redact_secrets:
            return text
        # Basic secret pattern redaction
        patterns = [
            (r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[^'\"|\s]+", "REDACTED_API_KEY"),
            (r"password['\"]?\s*[:=]\s*['\"]?[^'\"|\s]+", "REDACTED_PASSWORD"),
            (r"token['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9._\-]+", "REDACTED_TOKEN"),
        ]
        for pattern, repl in patterns:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        return text


def save_session_report(state: dict, outcome: str) -> None:
    """
    Save the full pipeline session as both JSON and Markdown reports.
    Sanitizes sensitive data before writing to disk.

    Args:
        state: Final AgentState dict from the pipeline.
        outcome: "APPROVED" | "ESCALATED"
    """
    output_dir = Path("./output")
    output_dir.mkdir(parents=True, exist_ok=True)

    session_id = state.get("session_id", datetime.utcnow().strftime("%Y%m%d_%H%M%S"))

    # SECURITY: Sanitize sensitive outputs before writing
    sanitized_user_request = sanitize_output(state.get("user_request", ""))
    sanitized_code = sanitize_output(state.get("final_code", ""))
    sanitized_verdict = sanitize_output(state.get("auditor_verdict", ""))

    # --- Save JSON (machine-readable audit log) ---
    json_path = output_dir / f"session_{session_id}.json"
    report_data = {
        "session_id": session_id,
        "outcome": outcome,
        "timestamp": state.get("timestamp"),
        "completed_at": datetime.utcnow().isoformat(),
        "user_request": sanitized_user_request,
        "language": state.get("language"),
        "iterations_run": state.get("iteration"),
        "final_status": state.get("status"),
        "iteration_history": state.get("iteration_history", []),
        "final_code": sanitized_code,
        "final_auditor_verdict": sanitized_verdict,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)

    # --- Save Markdown (human-readable) ---
    md_path = output_dir / f"session_{session_id}_report.md"
    md_content = _generate_markdown_report(state, outcome, sanitized_code, sanitized_verdict)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n📁 Audit reports saved:")
    print(f"   JSON: {json_path}")
    print(f"   Markdown: {md_path}")


def _generate_markdown_report(state: dict, outcome: str, sanitized_code: str = "", sanitized_verdict: str = "") -> str:
    """Generate a structured Markdown audit report with sanitized outputs."""
    status_emoji = "✅" if outcome == "APPROVED" else "🚨"
    session_id = state.get("session_id", "unknown")
    timestamp = state.get("timestamp", datetime.utcnow().isoformat())

    lines = [
        f"# Security Audit Report",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Session ID | `{session_id}` |",
        f"| Outcome | **{status_emoji} {outcome}** |",
        f"| Timestamp | {timestamp} |",
        f"| Language | {state.get('language', 'unknown').upper()} |",
        f"| Iterations | {state.get('iteration', '?')}/3 |",
        f"| User Request | {state.get('user_request', '')[:100]}... |",
        f"",
        f"---",
        f"",
    ]

    # Iteration history
    lines.append("## Iteration History")
    lines.append("")

    history = state.get("iteration_history", [])
    current_iter = 0

    for entry in history:
        iter_num = entry.get("iteration", 0)
        phase = entry.get("phase", "unknown")

        if iter_num != current_iter:
            current_iter = iter_num
            lines.append(f"### Iteration {iter_num}")
            lines.append("")

        phase_title = {
            "builder": "🔨 Builder Output",
            "hacker": "💀 Red Team Report",
            "auditor": "⚖️ Auditor Verdict",
        }.get(phase, f"Phase: {phase}")

        lines.append(f"#### {phase_title}")
        lines.append(f"*{entry.get('timestamp', '')}*")
        lines.append("")

        output = entry.get("output", "")
        # SECURITY: Sanitize iteration history outputs
        output = sanitize_output(output)
        lines.append("<details>")
        lines.append(f"<summary>Click to expand {phase} output</summary>")
        lines.append("")
        lines.append("```")
        lines.append(output[:3000] + ("..." if len(output) > 3000 else ""))
        lines.append("```")
        lines.append("</details>")
        lines.append("")

    # Final approved code (use pre-sanitized version)
    if outcome == "APPROVED" and sanitized_code:
        lines.extend([
            "---",
            "",
            "## ✅ Approved Code",
            "",
            "```",
            sanitized_code[:5000],
            "```",
            "",
        ])

    lines.extend([
        "---",
        "",
        f"*Report generated by Secure AI Coding Assistant*",
        f"*{datetime.utcnow().isoformat()}*",
        f"*Sensitive data redacted for security*",
    ])

    return "\n".join(lines)
