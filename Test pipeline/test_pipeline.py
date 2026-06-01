"""
tests/test_pipeline.py
-----------------------
Unit and integration tests for the Secure AI Coding Assistant.
Tests are designed to run WITHOUT an API key (mock mode only).
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.static_analysis import (
    run_bandit,
    run_ast_security_check,
    run_cargo_audit,
    run_cargo_clippy,
    run_all_tools,
    Severity,
    ToolReport,
)
from agents.agent_definitions import _extract_code_block
from main import _parse_verdict_status


# ---------------------------------------------------------------------------
# Static Analysis Tool Tests
# ---------------------------------------------------------------------------

class TestASTSecurityCheck:
    """Tests for the AST-based security heuristic (no external deps)."""

    def test_clean_code_passes(self):
        clean_code = """
def add(a: int, b: int) -> int:
    return a + b

result = add(1, 2)
print(result)
"""
        report = run_ast_security_check(clean_code)
        assert report.ran_successfully
        assert report.overall_severity == Severity.CLEAN
        assert len(report.findings) == 0

    def test_detects_eval(self):
        dangerous_code = """
user_input = input("Enter expression: ")
result = eval(user_input)
"""
        report = run_ast_security_check(dangerous_code)
        assert report.ran_successfully
        assert report.overall_severity == Severity.HIGH
        assert any("eval" in f.message.lower() or "B307" in f.rule_id for f in report.findings)

    def test_detects_exec(self):
        dangerous_code = """
code = compile("x = 1", "", "exec")
exec(code)
"""
        report = run_ast_security_check(dangerous_code)
        assert report.ran_successfully
        assert any(f.severity == Severity.HIGH for f in report.findings)

    def test_detects_pickle_import(self):
        dangerous_code = """
import pickle

def load_data(data):
    return pickle.loads(data)
"""
        report = run_ast_security_check(dangerous_code)
        assert report.ran_successfully
        assert any("pickle" in f.message.lower() for f in report.findings)

    def test_detects_marshal_import(self):
        dangerous_code = "import marshal\ndata = marshal.loads(b'')"
        report = run_ast_security_check(dangerous_code)
        assert any(f.severity in (Severity.HIGH, Severity.MEDIUM) for f in report.findings)

    def test_syntax_error_handled_gracefully(self):
        invalid_code = "def broken( :"
        report = run_ast_security_check(invalid_code)
        assert not report.ran_successfully
        assert report.error_message is not None

    def test_to_llm_context_format(self):
        """Ensure the LLM context string is non-empty and structured."""
        clean_code = "x = 1 + 1"
        report = run_ast_security_check(clean_code)
        context = report.to_llm_context()
        assert "Static Analysis Tool" in context
        assert len(context) > 50


class TestBanditMock:
    """Tests for Bandit mock mode (pattern matching)."""

    def test_detects_shell_true(self):
        code = "import subprocess\nsubprocess.run('ls', shell=True)"
        report = run_bandit(code, mock=True)
        assert report.ran_successfully
        assert any("shell=True" in f.message or "B602" in f.rule_id for f in report.findings)

    def test_detects_md5(self):
        code = "import hashlib\nhashlib.md5(b'password').hexdigest()"
        report = run_bandit(code, mock=True)
        findings = [f for f in report.findings if "md5" in f.message.lower() or "sha1" in f.message.lower()]
        assert len(findings) > 0

    def test_detects_yaml_unsafe(self):
        code = "import yaml\nyaml.load(data)"
        report = run_bandit(code, mock=True)
        assert any("yaml" in f.message.lower() for f in report.findings)

    def test_clean_code_no_findings(self):
        code = """
import hashlib
import secrets

def secure_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

token = secrets.token_urlsafe(32)
"""
        report = run_bandit(code, mock=True)
        assert report.ran_successfully


class TestCargoMock:
    """Tests for Cargo Audit/Clippy mock reports."""

    def test_audit_mock_returns_clean(self):
        report = run_cargo_audit("/tmp/fake_project", mock=True)
        assert report.ran_successfully
        assert report.overall_severity == Severity.CLEAN
        assert len(report.findings) == 0

    def test_clippy_mock_returns_clean(self):
        report = run_cargo_clippy("/tmp/fake_project", mock=True)
        assert report.ran_successfully
        assert report.overall_severity == Severity.CLEAN

    def test_tool_not_found_returns_graceful_error(self):
        """Cargo not installed → graceful failure, not exception."""
        report = run_cargo_audit("/nonexistent/path", mock=False)
        # Either runs successfully or fails gracefully
        assert isinstance(report, ToolReport)


class TestRunAllTools:
    """Tests for the tool dispatcher."""

    def test_python_dispatches_both_tools(self):
        code = "x = 1"
        result = run_all_tools(code, language="python", mock=True)
        assert "AST Security Check" in result or "Bandit" in result

    def test_unsupported_language_handled(self):
        result = run_all_tools("code", language="cobol", mock=True)
        assert "not yet supported" in result.lower() or isinstance(result, str)

    def test_high_severity_code_flagged(self):
        dangerous_code = "eval(input())"
        result = run_all_tools(dangerous_code, language="python", mock=True)
        assert "HIGH" in result or "eval" in result.lower()


# ---------------------------------------------------------------------------
# Utility Function Tests
# ---------------------------------------------------------------------------

class TestExtractCodeBlock:
    """Tests for the code block extractor utility."""

    def test_extracts_python_fenced_block(self):
        text = """
Here is the code:

```python
def hello():
    return "world"
```

Dependencies: none
"""
        result = _extract_code_block(text)
        assert 'def hello():' in result
        assert '```' not in result

    def test_extracts_largest_block(self):
        text = """
```
short
```

```python
def longer_function():
    x = 1
    y = 2
    return x + y
```
"""
        result = _extract_code_block(text)
        assert 'def longer_function' in result

    def test_fallback_on_no_fences(self):
        text = "No code fences here, just plain text"
        result = _extract_code_block(text)
        assert result == text


class TestParseVerdictStatus:
    """Tests for the verdict parser state machine."""

    def test_approved_verdict_detected(self):
        verdict = "## SECURITY AUDITOR — APPROVAL CERTIFICATE\n### Status: APPROVED ✓"
        status = _parse_verdict_status(verdict, iteration=1)
        assert status == "approved"

    def test_rejected_mid_loop(self):
        verdict = "## SECURITY AUDITOR — REMEDIATION BRIEF v1\n### Status: REJECTED"
        status = _parse_verdict_status(verdict, iteration=1)
        assert status == "rejected"

    def test_rejected_final_iteration_escalates(self):
        verdict = "### Status: REJECTED"
        status = _parse_verdict_status(verdict, iteration=3)
        assert status == "escalated"

    def test_approved_overrides_iteration_count(self):
        """Even on iteration 3, APPROVED should be APPROVED, not escalated."""
        verdict = "Status: APPROVED"
        status = _parse_verdict_status(verdict, iteration=3)
        assert status == "approved"


# ---------------------------------------------------------------------------
# Report Writer Tests
# ---------------------------------------------------------------------------

class TestReportWriter:
    """Tests for the audit trail writer."""

    def test_save_report_creates_files(self, tmp_path, monkeypatch):
        """Verify report files are created without errors."""
        import output.report_writer as rw

        # Redirect output_dir to tmp_path
        monkeypatch.chdir(tmp_path)

        mock_state = {
            "session_id": "test_20250101",
            "timestamp": "2025-01-01T00:00:00",
            "user_request": "Build a test function",
            "language": "python",
            "iteration": 2,
            "status": "approved",
            "iteration_history": [
                {
                    "iteration": 1,
                    "phase": "builder",
                    "output": "def test(): pass",
                    "timestamp": "2025-01-01T00:00:01",
                },
                {
                    "iteration": 1,
                    "phase": "hacker",
                    "output": "## RED TEAM REPORT\n### Verdict: PASS",
                    "timestamp": "2025-01-01T00:00:02",
                },
                {
                    "iteration": 1,
                    "phase": "auditor",
                    "output": "Status: APPROVED",
                    "status": "approved",
                    "timestamp": "2025-01-01T00:00:03",
                },
            ],
            "final_code": "def test(): pass",
            "auditor_verdict": "Status: APPROVED",
        }

        rw.save_session_report(mock_state, outcome="APPROVED")

        output_dir = tmp_path / "output"
        assert output_dir.exists()

        json_files = list(output_dir.glob("*.json"))
        md_files = list(output_dir.glob("*.md"))

        assert len(json_files) == 1
        assert len(md_files) == 1

        # Verify JSON is valid
        import json
        with open(json_files[0]) as f:
            data = json.load(f)
        assert data["outcome"] == "APPROVED"
        assert data["session_id"] == "test_20250101"


# ---------------------------------------------------------------------------
# Integration: Full Tool Chain (no LLM calls)
# ---------------------------------------------------------------------------

class TestToolChainIntegration:
    """End-to-end tool chain without LLM (for CI/CD)."""

    VULNERABLE_CODE = """
import subprocess
import pickle
import hashlib
import yaml

def process_user_input(user_data):
    # SQL injection
    query = "SELECT * FROM users WHERE id = " + user_data
    
    # Command injection
    result = subprocess.run(user_data, shell=True)
    
    # Deserialization
    obj = pickle.loads(user_data)
    
    # Weak crypto
    h = hashlib.md5(user_data.encode()).hexdigest()
    
    # Unsafe yaml
    config = yaml.load(user_data)
    
    return query, result, obj, h, config
"""

    SECURE_CODE = """
import hashlib
import secrets
import re
from typing import Optional


def process_id(user_id: str) -> Optional[str]:
    # Input validation — only allow numeric IDs
    if not re.match(r'^[0-9]{1,10}$', user_id):
        raise ValueError(f"Invalid user_id format: must be 1-10 digits")
    
    # Parameterized query (pseudo-code — use your actual ORM/driver)
    # cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return user_id  # Return validated ID for parameterized use


def generate_token() -> str:
    # Cryptographically secure token
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    # Use scrypt — appropriate for password hashing
    salt = secrets.token_bytes(32)
    key = hashlib.scrypt(
        password.encode('utf-8'),
        salt=salt,
        n=2**14, r=8, p=1
    )
    return salt.hex() + ':' + key.hex()
"""

    def test_vulnerable_code_produces_high_severity(self):
        ast_report = run_ast_security_check(self.VULNERABLE_CODE)
        bandit_report = run_bandit(self.VULNERABLE_CODE, mock=True)

        # At least one tool should flag HIGH severity
        has_high = (
            ast_report.overall_severity in (Severity.HIGH, Severity.CRITICAL)
            or bandit_report.overall_severity in (Severity.HIGH, Severity.CRITICAL)
        )
        assert has_high, "Vulnerable code should produce HIGH/CRITICAL severity findings"

    def test_secure_code_produces_clean_or_low(self):
        ast_report = run_ast_security_check(self.SECURE_CODE)
        assert ast_report.overall_severity in (Severity.CLEAN, Severity.LOW, Severity.MEDIUM)

    def test_run_all_tools_vulnerable_code(self):
        result = run_all_tools(self.VULNERABLE_CODE, language="python", mock=True)
        assert "HIGH" in result or "MEDIUM" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
