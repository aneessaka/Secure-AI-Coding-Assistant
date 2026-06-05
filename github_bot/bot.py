"""
github_bot/bot.py
-----------------
GitHub Pull Request security bot.

On pull_request (opened / synchronize / reopened):
  1. Optionally run /scan <url> web scan from PR body
  2. Fetch changed files from the PR
  3. Run the scan pipeline on each supported source file
  4. Post or update a summary comment on the PR
"""

from __future__ import annotations

import base64
import threading
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

from github_bot.scanner import WebScanner
from github_bot.url_validator import URLValidator

BOT_MARKER = "<!-- secure-ai-bot -->"
BOT_HEADER = "## Secure AI Security Scan"

EXTENSION_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".go": "go",
    ".rs": "rust",
}

MAX_FILES_PER_PR = int(os.getenv("GITHUB_MAX_FILES_PER_PR", "5"))
MAX_FILE_BYTES = int(os.getenv("GITHUB_MAX_FILE_BYTES", "30000"))
GITHUB_API = "https://api.github.com"


@dataclass
class Finding:
    severity: str
    cwe: str
    description: str


@dataclass
class FileScanResult:
    path: str
    language: str
    verdict: str
    findings: list[Finding]
    error: Optional[str] = None


def extract_scan_command(body: str) -> Optional[str]:
    """
    Look for a line starting with '/scan ' in the PR body.
    Returns a validated, sanitized URL if found, else None.
    """
    if not body:
        return None
    for line in body.splitlines():
        line = line.strip()
        if not line.lower().startswith("/scan "):
            continue
        url = line[6:].strip()
        if not url.startswith(("http://", "https://")):
            continue
        safe_url = URLValidator.sanitize_url(url)
        if URLValidator.is_safe_url(safe_url):
            return safe_url
    return None


def generate_scan_report(result: dict, target_url: str) -> str:
    """Generate markdown report from web scan results."""
    if result.get("total_findings", 0) == 0:
        return (
            f"## Security Scan Report for `{target_url}`\n\n"
            "**No vulnerabilities detected**\n\n"
            "_Simulated scan — real scanner coming soon._"
        )

    lines = [
        f"## Security Scan Report for `{target_url}`",
        f"**Scan completed:** {result.get('scan_time', 'unknown')}",
        f"**Total findings:** {result['total_findings']}",
        "",
        "### Vulnerability Details",
        "| Severity | Finding | Solution |",
        "|----------|---------|----------|",
    ]
    for finding in result.get("findings", []):
        solution = finding.get("solution", "")[:60]
        lines.append(
            f"| **{finding.get('severity', 'UNKNOWN')}** "
            f"| {finding.get('name', 'Unknown')} "
            f"| {solution} |"
        )
    lines.append("\n---\n_Scan performed by Secure AI Security Scanner (simulated)_")
    return "\n".join(lines)


def handle_scan_command(
    pull_request: dict,
    target_url: str,
    owner: str,
    repo_name: str,
    token: str,
) -> dict:
    """
    Post a comment that scanning started, run the web scanner, then post results.
    Safe to call from a background thread.
    """
    pr_number = pull_request.get("number")
    if not pr_number:
        return {"status": "error", "reason": "missing pr number"}

    print(f"[github-bot] /scan command for PR #{pr_number}: {target_url}")

    _post_pr_comment(
        owner,
        repo_name,
        pr_number,
        token,
        f"**Web Security Scan Initiated**\n\nScanning `{target_url}` for vulnerabilities...",
    )

    scanner = WebScanner()
    result = scanner.scan_url_sync(target_url)

    if result.get("error"):
        report = f"**Scan failed**: {result.get('details', 'Unknown error')}"
        status = "error"
    else:
        report = generate_scan_report(result, target_url)
        status = "success"

    _post_pr_comment(owner, repo_name, pr_number, token, report)

    return {
        "status": status,
        "pr": pr_number,
        "url": target_url,
        "findings": result.get("total_findings", 0),
    }


def _repo_context(payload: dict) -> tuple[dict, str, str, str]:
    """Extract pull_request, owner, repo_name, and token from a webhook payload."""
    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    full_name = repo.get("full_name", "")
    if "/" not in full_name:
        raise ValueError("missing repository full_name")
    owner, repo_name = full_name.split("/", 1)
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN is not set")
    return pr, owner, repo_name, token


def start_pull_request_tasks(payload: dict, run_scan: Callable[[str, str], dict]) -> dict:
    """
    Schedule PR processing in background threads.

    - If PR body contains `/scan <url>`, runs handle_scan_command
    - Always runs process_pull_request for changed source files

    Returns an immediate summary for the webhook HTTP response.
    """
    pr_body = (payload.get("pull_request") or {}).get("body") or ""
    target_url = extract_scan_command(pr_body)
    pr_number = (payload.get("pull_request") or {}).get("number")

    if target_url:

        def _web_scan_worker():
            try:
                pr, owner, repo_name, token = _repo_context(payload)
                summary = handle_scan_command(pr, target_url, owner, repo_name, token)
                print(f"[github-bot] web scan done: {summary}")
            except Exception as exc:
                print(f"[github-bot] web scan failed: {exc}")

        threading.Thread(target=_web_scan_worker, daemon=True).start()

    def _file_scan_worker():
        try:
            summary = process_pull_request(payload, run_scan)
            print(f"[github-bot] file scan done: {summary}")
        except Exception as exc:
            print(f"[github-bot] file scan failed: {exc}")

    threading.Thread(target=_file_scan_worker, daemon=True).start()

    response = {
        "pr": pr_number,
        "file_scan": "started",
    }
    if target_url:
        response["web_scan_url"] = target_url
        response["web_scan"] = "started"
    return response


def verify_webhook_signature(payload: bytes, signature_header: Optional[str], secret: str) -> bool:
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def language_for_path(path: str) -> Optional[str]:
    lower = path.lower()
    for ext, lang in EXTENSION_LANGUAGE.items():
        if lower.endswith(ext):
            return lang
    return None


def parse_findings(hacker_report: str) -> list[Finding]:
    """Extract structured findings from Hacker agent output."""
    findings: list[Finding] = []
    seen: set[str] = set()

    patterns = [
        re.compile(
            r"\[(CRITICAL|HIGH|MEDIUM|LOW)\][^\n]*?(CWE-\d+)[:\s—\-]+(.+)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\*\*(CRITICAL|HIGH|MEDIUM|LOW)\s*[—\-]\s*(CWE-\d+):\s*([^*\n]+)",
            re.IGNORECASE,
        ),
    ]

    for line in hacker_report.splitlines():
        line = line.strip()
        if not line:
            continue
        for pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            sev = match.group(1).upper()
            cwe = match.group(2).upper()
            desc = match.group(3).strip().rstrip("*").strip()
            key = f"{sev}|{cwe}|{desc[:80]}"
            if key in seen:
                break
            seen.add(key)
            findings.append(Finding(severity=sev, cwe=cwe, description=desc))
            break

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda f: severity_order.get(f.severity, 9))
    return findings


def _github_request(
    method: str,
    path: str,
    token: str,
    body: Optional[dict] = None,
) -> Any:
    url = f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Secure-AI-Coding-Assistant-Bot",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def _list_pr_files(owner: str, repo: str, pr_number: int, token: str) -> list[dict]:
    return _github_request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}/files", token)


def _fetch_file_content(owner: str, repo: str, path: str, ref: str, token: str) -> Optional[str]:
    encoded_path = urllib.parse.quote(path, safe="/")
    try:
        data = _github_request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{encoded_path}?ref={ref}",
            token,
        )
    except urllib.error.HTTPError:
        return None

    if not isinstance(data, dict) or data.get("encoding") != "base64":
        return None

    try:
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return None

    if len(content) > MAX_FILE_BYTES:
        return None
    return content


def _list_issue_comments(owner: str, repo: str, pr_number: int, token: str) -> list[dict]:
    return _github_request("GET", f"/repos/{owner}/{repo}/issues/{pr_number}/comments", token)


def _post_pr_comment(owner: str, repo: str, pr_number: int, token: str, body: str) -> None:
    _github_request(
        "POST",
        f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
        token,
        {"body": body},
    )


def _upsert_pr_comment(owner: str, repo: str, pr_number: int, token: str, body: str) -> None:
    comments = _list_issue_comments(owner, repo, pr_number, token)
    existing_id = None
    for comment in comments:
        if BOT_MARKER in (comment.get("body") or ""):
            existing_id = comment["id"]
            break

    payload = {"body": body}
    if existing_id:
        _github_request(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/comments/{existing_id}",
            token,
            payload,
        )
    else:
        _post_pr_comment(owner, repo, pr_number, token, body)


def _format_comment(results: list[FileScanResult], pr_number: int) -> str:
    scanned = [r for r in results if not r.error]
    errors = [r for r in results if r.error]
    all_findings = [f for r in scanned for f in r.findings]

    overall = "APPROVED"
    for r in scanned:
        if r.verdict != "APPROVED":
            overall = "ESCALATED"
            break
    if any(f.severity in ("CRITICAL", "HIGH") for f in all_findings):
        overall = "ESCALATED"

    lines = [
        BOT_MARKER,
        BOT_HEADER,
        "",
        f"**PR #{pr_number}** · **Verdict: {overall}** · {len(scanned)} file(s) scanned",
        "",
    ]

    if not scanned and not errors:
        lines.append("_No supported source files changed in this PR._")
        lines.append("")
        lines.append("Supported: `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.go`, `.rs`")
        return "\n".join(lines)

    for result in scanned:
        icon = "✅" if result.verdict == "APPROVED" and not result.findings else "⚠️"
        lines.append(f"### {icon} `{result.path}` — {result.verdict}")
        if result.findings:
            lines.append("")
            lines.append("| Severity | CWE | Finding |")
            lines.append("|----------|-----|---------|")
            for f in result.findings[:8]:
                desc = f.description.replace("|", "\\|")[:120]
                lines.append(f"| **{f.severity}** | {f.cwe} | {desc} |")
        else:
            lines.append("")
            lines.append("_No vulnerabilities detected._")
        lines.append("")

    if errors:
        lines.append("### Skipped files")
        for result in errors:
            lines.append(f"- `{result.path}`: {result.error}")
        lines.append("")

    lines.append("---")
    lines.append("_Powered by [Secure AI Coding Assistant](https://secure-ai-coding-assistant.onrender.com)_")
    return "\n".join(lines)


def process_pull_request(payload: dict, run_scan: Callable[[str, str], dict]) -> dict:
    """
    Scan a pull request and post findings. Called from a background thread.

    Returns a summary dict for logging.
    """
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN is not set")

    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    action = payload.get("action", "")

    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"action={action}"}

    full_name = repo.get("full_name", "")
    if "/" not in full_name:
        return {"status": "error", "reason": "missing repository full_name"}

    owner, repo_name = full_name.split("/", 1)
    pr_number = pr.get("number")
    head_sha = (pr.get("head") or {}).get("sha", "")

    if not pr_number or not head_sha:
        return {"status": "error", "reason": "missing pr number or head sha"}

    print(f"[github-bot] scanning PR #{pr_number} on {full_name} ({action})")

    files = _list_pr_files(owner, repo_name, pr_number, token)
    results: list[FileScanResult] = []
    scanned_count = 0

    for file_info in files:
        if scanned_count >= MAX_FILES_PER_PR:
            results.append(FileScanResult(
                path="(remaining files)",
                language="",
                verdict="SKIPPED",
                findings=[],
                error=f"Limit of {MAX_FILES_PER_PR} files per PR",
            ))
            break

        status = file_info.get("status", "")
        if status == "removed":
            continue

        path = file_info.get("filename", "")
        language = language_for_path(path)
        if not language:
            continue

        content = _fetch_file_content(owner, repo_name, path, head_sha, token)
        if not content or not content.strip():
            results.append(FileScanResult(
                path=path,
                language=language,
                verdict="SKIPPED",
                findings=[],
                error="empty or too large",
            ))
            continue

        scanned_count += 1
        try:
            scan_result = run_scan(content, language)
            findings = parse_findings(scan_result.get("hacker_report", ""))
            results.append(FileScanResult(
                path=path,
                language=language,
                verdict=scan_result.get("final_verdict", "ESCALATED"),
                findings=findings,
            ))
            print(f"[github-bot] scanned {path}: {scan_result.get('final_verdict')} ({len(findings)} findings)")
        except Exception as exc:
            results.append(FileScanResult(
                path=path,
                language=language,
                verdict="ERROR",
                findings=[],
                error=str(exc)[:200],
            ))
            print(f"[github-bot] error scanning {path}: {exc}")

    comment_body = _format_comment(results, pr_number)
    _upsert_pr_comment(owner, repo_name, pr_number, token, comment_body)

    return {
        "status": "success",
        "pr": pr_number,
        "repo": full_name,
        "files_scanned": scanned_count,
        "action": action,
    }
