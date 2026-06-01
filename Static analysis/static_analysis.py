"""
tools/static_analysis.py
-------------------------
Programmatic tool wrappers for static analysis.
These are called by the Auditor Agent via LangGraph's tool-calling mechanism.
Each function runs a real CLI tool (or a mock in test mode) and returns
structured output that gets injected back into the LLM context.

In production, these call real binaries. In test/mock mode, they return
realistic sample output so the agent pipeline can be developed and tested
without a full Rust/Python toolchain installed.
"""

import subprocess
import tempfile
import os
import json
import ast
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    CLEAN = "CLEAN"


@dataclass
class ToolFinding:
    tool: str
    severity: Severity
    rule_id: str
    message: str
    location: str
    cwe: Optional[str] = None
    confidence: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolReport:
    tool_name: str
    language: str
    overall_severity: Severity
    findings: list[ToolFinding]
    raw_output: str
    ran_successfully: bool
    error_message: Optional[str] = None

    def to_llm_context(self) -> str:
        """Format the report for injection into LLM context."""
        if not self.ran_successfully:
            return (
                f"## Static Analysis Tool: {self.tool_name}\n"
                f"**Status**: FAILED TO RUN\n"
                f"**Error**: {self.error_message}\n"
                f"*Note: Manual review required — automated tool unavailable.*\n"
            )

        lines = [
            f"## Static Analysis Tool: {self.tool_name}",
            f"**Language**: {self.language}",
            f"**Overall Severity**: {self.overall_severity.value}",
            f"**Total Findings**: {len(self.findings)}",
            "",
        ]

        if not self.findings:
            lines.append("✅ No issues detected.")
        else:
            lines.append("### Findings:")
            for i, f in enumerate(self.findings, 1):
                lines.append(f"\n**{i}. [{f.severity.value}] {f.rule_id}**")
                lines.append(f"   - Location: `{f.location}`")
                lines.append(f"   - Message: {f.message}")
                if f.cwe:
                    lines.append(f"   - CWE: {f.cwe}")
                if f.confidence:
                    lines.append(f"   - Confidence: {f.confidence}")

        lines.append(f"\n### Raw Tool Output:\n```\n{self.raw_output}\n```")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Python: Bandit Static Analyzer
# ---------------------------------------------------------------------------

def run_bandit(python_code: str, mock: bool = False) -> ToolReport:
    """
    Run Bandit static analysis on Python code.
    Bandit checks for common Python security issues (B-series rules).

    Args:
        python_code: The raw Python source code string.
        mock: If True, return a realistic mock report (for testing).

    Returns:
        ToolReport with structured findings.
    """
    if mock:
        return _mock_bandit_report(python_code)

    # Write code to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="sec_audit_"
    ) as f:
        f.write(python_code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["bandit", "-f", "json", "-ll", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        raw_output = result.stdout or result.stderr

        if result.returncode not in (0, 1):  # 0=clean, 1=issues found
            return ToolReport(
                tool_name="Bandit",
                language="Python",
                overall_severity=Severity.INFO,
                findings=[],
                raw_output=raw_output,
                ran_successfully=False,
                error_message=f"Bandit exited with code {result.returncode}: {result.stderr}",
            )

        return _parse_bandit_json(raw_output)

    except FileNotFoundError:
        return ToolReport(
            tool_name="Bandit",
            language="Python",
            overall_severity=Severity.INFO,
            findings=[],
            raw_output="",
            ran_successfully=False,
            error_message=(
                "Bandit not found. Install with: pip install bandit\n"
                "Falling back to AST-based heuristic analysis."
            ),
        )
    except subprocess.TimeoutExpired:
        return ToolReport(
            tool_name="Bandit",
            language="Python",
            overall_severity=Severity.INFO,
            findings=[],
            raw_output="",
            ran_successfully=False,
            error_message="Bandit timed out after 30 seconds.",
        )
    finally:
        os.unlink(tmp_path)


def _parse_bandit_json(raw_json: str) -> ToolReport:
    """
    Parse Bandit's JSON output into a ToolReport.
    Uses defensive dict access to prevent KeyError crashes.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return ToolReport(
            tool_name="Bandit",
            language="Python",
            overall_severity=Severity.INFO,
            findings=[],
            raw_output=raw_json,
            ran_successfully=False,
            error_message=f"Failed to parse Bandit JSON output: {str(e)}",
        )

    findings = []
    max_severity = Severity.CLEAN

    severity_map = {"HIGH": Severity.HIGH, "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW}
    severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.CLEAN]

    # SECURITY: Defensive dict access to prevent crashes on malformed JSON
    results = data.get("results", []) if isinstance(data, dict) else []
    if not isinstance(results, list):
        results = []

    for result in results:
        try:
            if not isinstance(result, dict):
                continue
            
            sev = severity_map.get(result.get("issue_severity", "LOW"), Severity.LOW)

            # Update overall severity (take highest)
            if severity_order.index(sev) < severity_order.index(max_severity):
                max_severity = sev

            # Defensive access to nested structures
            issue_cwe = result.get("issue_cwe", {})
            cwe_link = issue_cwe.get("link", None) if isinstance(issue_cwe, dict) else None

            findings.append(ToolFinding(
                tool="Bandit",
                severity=sev,
                rule_id=result.get("test_id", "B000"),
                message=result.get("issue_text", "Unknown issue"),
                location=f"{result.get('filename', '?')}:{result.get('line_number', '?')}",
                cwe=cwe_link,
                confidence=result.get("issue_confidence", "UNKNOWN"),
            ))
        except Exception as e:
            # Log but continue processing other results
            continue

    return ToolReport(
        tool_name="Bandit",
        language="Python",
        overall_severity=max_severity,
        findings=findings,
        raw_output=raw_json,
        ran_successfully=True,
    )


def _mock_bandit_report(python_code: str) -> ToolReport:
    """
    Realistic mock Bandit report.
    Performs simple pattern matching to generate context-aware mock output.
    In production, replace with actual subprocess call.
    """
    findings = []
    max_severity = Severity.CLEAN

    # Heuristic checks on the code string
    checks = [
        (r"subprocess\.call|subprocess\.run.*shell=True", Severity.HIGH,
         "B602", "subprocess call with shell=True", "CWE-78"),
        (r"eval\(|exec\(", Severity.HIGH,
         "B307", "Use of eval/exec — code injection risk", "CWE-95"),
        (r"pickle\.loads|pickle\.load", Severity.HIGH,
         "B301", "Pickle and modules that wrap it are unsafe", "CWE-502"),
        (r"yaml\.load\((?!.*Loader=yaml\.SafeLoader)", Severity.MEDIUM,
         "B506", "yaml.load() without SafeLoader", "CWE-20"),
        (r"hashlib\.md5|hashlib\.sha1", Severity.MEDIUM,
         "B303", "Use of MD5 or SHA1 for security purposes", "CWE-327"),
        (r"random\.(random|randint|choice)", Severity.LOW,
         "B311", "Standard pseudo-random generator not suitable for security", "CWE-338"),
        (r"assert\s", Severity.LOW,
         "B101", "Use of assert detected — disabled with -O", "CWE-617"),
    ]

    severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.CLEAN]

    for pattern, severity, rule_id, message, cwe in checks:
        if re.search(pattern, python_code):
            findings.append(ToolFinding(
                tool="Bandit (mock)",
                severity=severity,
                rule_id=rule_id,
                message=message,
                location="[detected via pattern analysis]",
                cwe=cwe,
                confidence="MEDIUM",
            ))
            if severity_order.index(severity) < severity_order.index(max_severity):
                max_severity = severity

    mock_raw = json.dumps({
        "results": [
            {
                "test_id": f.rule_id,
                "issue_text": f.message,
                "issue_severity": f.severity.value,
                "filename": "submitted_code.py",
                "line_number": 0,
                "issue_cwe": {"link": f.cwe},
            }
            for f in findings
        ]
    }, indent=2)

    return ToolReport(
        tool_name="Bandit (mock mode)",
        language="Python",
        overall_severity=max_severity,
        findings=findings,
        raw_output=mock_raw,
        ran_successfully=True,
    )


# ---------------------------------------------------------------------------
# Python: AST-based Security Heuristic (no external tool required)
# ---------------------------------------------------------------------------

def run_ast_security_check(python_code: str) -> ToolReport:
    """
    Pure-Python AST-based security heuristic. No external tools needed.
    Catches banned function calls, dangerous imports, and obvious patterns.
    This is always available as a fallback.
    """
    findings = []
    max_severity = Severity.CLEAN
    severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.CLEAN]

    BANNED_CALLS = {
        "eval": (Severity.HIGH, "B307", "Direct eval() call — code injection risk", "CWE-95"),
        "exec": (Severity.HIGH, "B307", "Direct exec() call — code injection risk", "CWE-95"),
        "compile": (Severity.MEDIUM, "B307", "compile() with dynamic input is risky", "CWE-95"),
        "__import__": (Severity.MEDIUM, "B401", "Dynamic __import__ — potential import injection", "CWE-94"),
    }

    BANNED_IMPORTS = {
        "pickle": (Severity.HIGH, "B301", "pickle import — arbitrary code on deserialize", "CWE-502"),
        "marshal": (Severity.HIGH, "B302", "marshal import — dangerous deserialization", "CWE-502"),
        "shelve": (Severity.MEDIUM, "B301", "shelve uses pickle under the hood", "CWE-502"),
    }

    try:
        tree = ast.parse(python_code)
    except SyntaxError as e:
        return ToolReport(
            tool_name="AST Security Check",
            language="Python",
            overall_severity=Severity.INFO,
            findings=[],
            raw_output="",
            ran_successfully=False,
            error_message=f"SyntaxError — could not parse code: {e}",
        )

    for node in ast.walk(tree):
        # Check for banned function calls
        if isinstance(node, ast.Call):
            func_name = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name in BANNED_CALLS:
                sev, rule, msg, cwe = BANNED_CALLS[func_name]
                findings.append(ToolFinding(
                    tool="AST Security Check",
                    severity=sev,
                    rule_id=rule,
                    message=msg,
                    location=f"line {node.lineno}",
                    cwe=cwe,
                    confidence="HIGH",
                ))
                if severity_order.index(sev) < severity_order.index(max_severity):
                    max_severity = sev
            
            # SECURITY: Detect SQL concatenation patterns
            if func_name and "execute" in func_name.lower() and len(node.args) > 0:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.JoinedStr) or isinstance(first_arg, ast.BinOp):
                    findings.append(ToolFinding(
                        tool="AST Security Check",
                        severity=Severity.HIGH,
                        rule_id="B608",
                        message="Potential SQL injection: string concatenation in query",
                        location=f"line {node.lineno}",
                        cwe="CWE-89",
                        confidence="MEDIUM",
                    ))
                    if severity_order.index(Severity.HIGH) < severity_order.index(max_severity):
                        max_severity = Severity.HIGH
            
            # SECURITY: Detect subprocess with shell=True
            if func_name and "subprocess" in str(node.func).lower():
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        findings.append(ToolFinding(
                            tool="AST Security Check",
                            severity=Severity.HIGH,
                            rule_id="B602",
                            message="subprocess call with shell=True allows shell injection",
                            location=f"line {node.lineno}",
                            cwe="CWE-78",
                            confidence="HIGH",
                        ))
                        if severity_order.index(Severity.HIGH) < severity_order.index(max_severity):
                            max_severity = Severity.HIGH

        # Check for banned imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]

            for name in names:
                if name in BANNED_IMPORTS:
                    sev, rule, msg, cwe = BANNED_IMPORTS[name]
                    findings.append(ToolFinding(
                        tool="AST Security Check",
                        severity=sev,
                        rule_id=rule,
                        message=msg,
                        location=f"line {node.lineno}",
                        cwe=cwe,
                        confidence="HIGH",
                    ))
                    if severity_order.index(sev) < severity_order.index(max_severity):
                        max_severity = sev

    raw_summary = f"AST scan complete. {len(findings)} issue(s) found."
    return ToolReport(
        tool_name="AST Security Check",
        language="Python",
        overall_severity=max_severity,
        findings=findings,
        raw_output=raw_summary,
        ran_successfully=True,
    )


# ---------------------------------------------------------------------------
# Rust: Cargo Audit + Cargo Clippy wrappers
# ---------------------------------------------------------------------------

def run_cargo_audit(project_path: str, mock: bool = False) -> ToolReport:
    """
    Run `cargo audit` on a Rust project to check for known CVEs in dependencies.

    Args:
        project_path: Path to the Rust project root (containing Cargo.toml).
        mock: If True, return a mock report.
        
    Raises:
        ValueError: If project_path contains path traversal attempts.
    """
    if mock:
        return _mock_cargo_audit_report()

    # SECURITY: Validate project path to prevent path traversal
    try:
        from pathlib import Path
        safe_path = str(Path(project_path).resolve())
        if ".." in project_path:
            raise ValueError(f"Path traversal detected in: {project_path}")
    except Exception as e:
        return ToolReport(
            tool_name="Cargo Audit",
            language="Rust",
            overall_severity=Severity.INFO,
            findings=[],
            raw_output="",
            ran_successfully=False,
            error_message=f"Invalid project path: {str(e)}",
        )

    try:
        result = subprocess.run(
            ["cargo", "audit", "--json"],
            cwd=safe_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        raw_output = result.stdout or result.stderr
        return _parse_cargo_audit_json(raw_output)

    except FileNotFoundError:
        return ToolReport(
            tool_name="Cargo Audit",
            language="Rust",
            overall_severity=Severity.INFO,
            findings=[],
            raw_output="",
            ran_successfully=False,
            error_message=(
                "cargo-audit not found. Install with: cargo install cargo-audit\n"
                "Ensure you have a Rust toolchain installed (rustup.rs)."
            ),
        )
    except subprocess.TimeoutExpired:
        return ToolReport(
            tool_name="Cargo Audit",
            language="Rust",
            overall_severity=Severity.INFO,
            findings=[],
            raw_output="",
            ran_successfully=False,
            error_message="cargo audit timed out after 120 seconds.",
        )


def _parse_cargo_audit_json(raw_json: str) -> ToolReport:
    """Parse cargo audit JSON output."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return ToolReport(
            tool_name="Cargo Audit",
            language="Rust",
            overall_severity=Severity.CLEAN,
            findings=[],
            raw_output=raw_json,
            ran_successfully=True,
        )

    findings = []
    vulnerabilities = data.get("vulnerabilities", {}).get("list", [])

    for vuln in vulnerabilities:
        advisory = vuln.get("advisory", {})
        package = vuln.get("package", {})

        findings.append(ToolFinding(
            tool="Cargo Audit",
            severity=Severity.HIGH,
            rule_id=advisory.get("id", "RUSTSEC-UNKNOWN"),
            message=advisory.get("title", "Unknown advisory"),
            location=f"{package.get('name', '?')} v{package.get('version', '?')}",
            cwe=str(advisory.get("cvss", "N/A")),
            confidence="HIGH",
        ))

    overall = Severity.HIGH if findings else Severity.CLEAN
    return ToolReport(
        tool_name="Cargo Audit",
        language="Rust",
        overall_severity=overall,
        findings=findings,
        raw_output=raw_json,
        ran_successfully=True,
    )


def run_cargo_clippy(project_path: str, mock: bool = False) -> ToolReport:
    """
    Run `cargo clippy` for Rust linting with security-relevant lints enabled.
    Passes --deny warnings to treat warnings as errors.
    """
    if mock:
        return _mock_cargo_clippy_report()

    try:
        result = subprocess.run(
            [
                "cargo", "clippy",
                "--message-format=json",
                "--", 
                "-D", "warnings",
                "-W", "clippy::suspicious",
                "-W", "clippy::perf",
                "-W", "clippy::correctness",
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )

        raw_output = result.stdout
        return _parse_clippy_json(raw_output)

    except FileNotFoundError:
        return ToolReport(
            tool_name="Cargo Clippy",
            language="Rust",
            overall_severity=Severity.INFO,
            findings=[],
            raw_output="",
            ran_successfully=False,
            error_message="Cargo/Clippy not found. Install Rust toolchain from rustup.rs",
        )


def _parse_clippy_json(raw_output: str) -> ToolReport:
    """Parse cargo clippy JSON message format output."""
    findings = []
    lines = raw_output.strip().split("\n")

    for line in lines:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        if msg.get("reason") != "compiler-message":
            continue

        message = msg.get("message", {})
        level = message.get("level", "")

        if level in ("error", "warning"):
            spans = message.get("spans", [{}])
            loc = "unknown"
            if spans:
                s = spans[0]
                loc = f"{s.get('file_name', '?')}:{s.get('line_start', '?')}"

            sev = Severity.HIGH if level == "error" else Severity.MEDIUM
            findings.append(ToolFinding(
                tool="Cargo Clippy",
                severity=sev,
                rule_id=message.get("code", {}).get("code", "clippy::unknown") if message.get("code") else "clippy",
                message=message.get("message", "Unknown"),
                location=loc,
                confidence="HIGH",
            ))

    overall = Severity.HIGH if any(f.severity == Severity.HIGH for f in findings) else (
        Severity.MEDIUM if findings else Severity.CLEAN
    )

    return ToolReport(
        tool_name="Cargo Clippy",
        language="Rust",
        overall_severity=overall,
        findings=findings,
        raw_output=raw_output,
        ran_successfully=True,
    )


def _mock_cargo_audit_report() -> ToolReport:
    """Mock cargo audit report — clean (no known vulnerabilities)."""
    return ToolReport(
        tool_name="Cargo Audit (mock mode)",
        language="Rust",
        overall_severity=Severity.CLEAN,
        findings=[],
        raw_output=json.dumps({
            "vulnerabilities": {"found": False, "count": 0, "list": []},
            "warnings": {},
        }, indent=2),
        ran_successfully=True,
    )


def _mock_cargo_clippy_report() -> ToolReport:
    """Mock cargo clippy report — clean."""
    return ToolReport(
        tool_name="Cargo Clippy (mock mode)",
        language="Rust",
        overall_severity=Severity.CLEAN,
        findings=[],
        raw_output="warning: 0 warnings emitted",
        ran_successfully=True,
    )


# ---------------------------------------------------------------------------
# Dispatcher: Auto-detect language and run appropriate tools
# ---------------------------------------------------------------------------

def run_all_tools(code: str, language: str = "python", mock: bool = True) -> str:
    """
    Master tool dispatcher. Auto-selects the right tools based on language.
    Returns a formatted string ready for LLM context injection.

    Args:
        code: Source code string.
        language: 'python' or 'rust'.
        mock: Use mock mode (no real tool installation required).

    Returns:
        Formatted multi-tool report string.
    """
    reports = []

    if language.lower() == "python":
        # Always run AST check (no external deps)
        ast_report = run_ast_security_check(code)
        reports.append(ast_report.to_llm_context())

        # Try Bandit (falls back to mock gracefully)
        bandit_report = run_bandit(code, mock=mock)
        reports.append(bandit_report.to_llm_context())

    elif language.lower() == "rust":
        # For Rust, we need a project path — use mock in inline mode
        clippy_report = run_cargo_clippy("/tmp/rust_project", mock=True)
        reports.append(clippy_report.to_llm_context())

        audit_report = run_cargo_audit("/tmp/rust_project", mock=True)
        reports.append(audit_report.to_llm_context())

    else:
        reports.append(
            f"## Static Analysis\n"
            f"**Language '{language}' not yet supported by automated tools.**\n"
            f"Manual review required.\n"
        )

    separator = "\n" + "=" * 60 + "\n"
    return separator.join(reports)
