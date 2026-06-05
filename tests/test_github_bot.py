"""Tests for GitHub PR bot (no live GitHub or LLM calls)."""

import hashlib
import hmac
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from github_bot.bot import (
    BOT_MARKER,
    Finding,
    FileScanResult,
    language_for_path,
    parse_findings,
    process_pull_request,
    verify_webhook_signature,
    _format_comment,
)


class TestLanguageDetection:
    def test_python(self):
        assert language_for_path("src/app.py") == "python"

    def test_javascript_variants(self):
        assert language_for_path("index.jsx") == "javascript"
        assert language_for_path("app.ts") == "javascript"

    def test_go_and_rust(self):
        assert language_for_path("main.go") == "go"
        assert language_for_path("lib.rs") == "rust"

    def test_unsupported(self):
        assert language_for_path("README.md") is None


class TestParseFindings:
    def test_bracket_format(self):
        report = "[HIGH] CWE-89: SQL injection via string concatenation"
        findings = parse_findings(report)
        assert len(findings) == 1
        assert findings[0].severity == "HIGH"
        assert findings[0].cwe == "CWE-89"

    def test_markdown_format(self):
        report = "**CRITICAL — CWE-78: Command injection via shell=True**"
        findings = parse_findings(report)
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"

    def test_deduplicates(self):
        report = (
            "[HIGH] CWE-89: SQL injection\n"
            "[HIGH] CWE-89: SQL injection\n"
        )
        assert len(parse_findings(report)) == 1


class TestWebhookSignature:
    def test_valid_signature(self):
        secret = "test-secret"
        body = b'{"action":"opened"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(body, sig, secret)

    def test_invalid_signature(self):
        assert not verify_webhook_signature(b"{}", "sha256=bad", "secret")


class TestFormatComment:
    def test_includes_marker_and_verdict(self):
        results = [
            FileScanResult(
                path="app.py",
                language="python",
                verdict="ESCALATED",
                findings=[Finding("HIGH", "CWE-89", "SQL injection")],
            )
        ]
        body = _format_comment(results, 42)
        assert BOT_MARKER in body
        assert "PR #42" in body
        assert "ESCALATED" in body
        assert "CWE-89" in body


class TestProcessPullRequest:
    def test_ignores_unsupported_action(self, monkeypatch):
        os.environ["GITHUB_TOKEN"] = "fake-token"
        payload = {"action": "closed", "pull_request": {"number": 1}, "repository": {"full_name": "o/r"}}
        result = process_pull_request(payload, lambda c, l: {})
        assert result["status"] == "ignored"

    def test_scans_and_posts_comment(self, monkeypatch):
        os.environ["GITHUB_TOKEN"] = "fake-token"
        calls = {"scan": 0, "comment": 0}

        def fake_scan(code, lang):
            calls["scan"] += 1
            return {
                "final_verdict": "ESCALATED",
                "hacker_report": "[HIGH] CWE-78: shell injection",
            }

        monkeypatch.setattr(
            "github_bot.bot._list_pr_files",
            lambda *a: [{"filename": "app.py", "status": "modified"}],
        )
        monkeypatch.setattr(
            "github_bot.bot._fetch_file_content",
            lambda *a: "subprocess.run(x, shell=True)",
        )
        monkeypatch.setattr(
            "github_bot.bot._upsert_pr_comment",
            lambda *a: calls.__setitem__("comment", calls["comment"] + 1),
        )

        payload = {
            "action": "opened",
            "pull_request": {"number": 7, "head": {"sha": "abc123"}},
            "repository": {"full_name": "owner/repo"},
        }
        result = process_pull_request(payload, fake_scan)

        assert result["status"] == "success"
        assert result["files_scanned"] == 1
        assert calls["scan"] == 1
        assert calls["comment"] == 1
