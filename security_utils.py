"""
security_utils.py
-----------------
Security utilities for input validation, output sanitization, and safe session ID generation.
"""

import os
import re
import secrets
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# --- Malicious Request Filter ---

MALICIOUS_REQUEST_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(wifi|wi-fi|wpa2?|wep)\b.{0,40}\b(hack(ing)?|crack(ing)?|break|bypass|steal)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(hack(ing)?|crack(ing)?|break)\b.{0,40}\b(wifi|wi-fi|wpa2?|wep)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(build|create|write|make|develop)\b.{0,30}\b(keylogger|ransomware|rootkit|botnet|spyware|malware|virus|trojan|worm)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(keylogger|ransomware|rootkit|botnet|spyware)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(credential\s*stuffing|password\s*spray(ing)?|brute\s*force\s*tool)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(ddos|dos)\b.{0,20}\b(tool|script|attack|bot)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(steal|exfiltrate|harvest)\b.{0,30}\b(password|credential|cookie|session|token)s?\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(phishing)\b.{0,30}\b(page|site|email|kit|template)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(exploit|payload)\b.{0,30}\b(generator|builder|framework)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(bypass|disable|evade)\b.{0,30}\b(antivirus|firewall|detection|security)\b", re.I),
     "offensive_tooling"),
    (re.compile(r"\b(unauthorized|illegal)\b.{0,30}\b(access|intrusion|entry)\b", re.I),
     "offensive_tooling"),
]

BLOCKED_REQUEST_MESSAGE = (
    "This platform generates and audits defensive security code. "
    "Requests for offensive tooling, unauthorized access, or attack tools are not permitted. "
    "You can scan existing code for vulnerabilities using /api/scan."
)


@dataclass(frozen=True)
class ContentFilterResult:
    blocked: bool
    category: Optional[str] = None
    matched_pattern: Optional[str] = None


def check_malicious_request(text: str) -> ContentFilterResult:
    """
    Block natural-language requests that ask for offensive or malicious tooling.

    Applied to code-generation requests (/api/run), not to source code submitted
    for security review (/api/scan).
    """
    normalized = " ".join(text.split())
    for pattern, category in MALICIOUS_REQUEST_PATTERNS:
        if pattern.search(normalized):
            return ContentFilterResult(
                blocked=True,
                category=category,
                matched_pattern=pattern.pattern,
            )
    return ContentFilterResult(blocked=False)


# --- Session ID Generation ---

def generate_secure_session_id() -> str:
    """
    Generate a cryptographically random session ID.
    Uses secrets module (cryptographically secure) instead of timestamp.
    
    Returns:
        A 32-character hex string suitable for session identification.
    """
    return secrets.token_hex(16)


# --- Input Validation ---

def validate_request_length(user_request: str, max_length: int = 5000) -> None:
    """
    Validate that user request is within acceptable length.
    Prevents token exhaustion attacks.
    
    Args:
        user_request: The user's code generation request.
        max_length: Maximum allowed length (default 5000 chars).
    
    Raises:
        ValueError: If request exceeds max_length.
    """
    if len(user_request) > max_length:
        raise ValueError(
            f"Request exceeds maximum length of {max_length} characters. "
            f"Provided: {len(user_request)} characters."
        )


def validate_remediation_brief(remediation_brief: str, max_length: int = 10000) -> None:
    """
    Validate remediation brief from Auditor to prevent context exhaustion.
    
    Args:
        remediation_brief: The Auditor's remediation instructions.
        max_length: Maximum allowed length (default 10000 chars).
    
    Raises:
        ValueError: If brief exceeds max_length.
    """
    if len(remediation_brief) > max_length:
        raise ValueError(
            f"Remediation brief exceeds maximum length of {max_length} characters. "
            f"Provided: {len(remediation_brief)} characters."
        )


def escape_for_template(text: str) -> str:
    """
    Escape special characters that could break template injection.
    
    Args:
        text: The text to escape.
    
    Returns:
        Escaped text safe for template embedding.
    """
    # Escape backslashes first to avoid double-escaping
    text = text.replace("\\", "\\\\")
    # Escape triple backticks (markdown code fence)
    text = text.replace("```", "`​`​`")
    # Escape common template markers
    text = text.replace("{{", "{ {")
    text = text.replace("}}", "} }")
    return text


def validate_path_safety(path_str: str, allowed_parent: Optional[str] = None) -> Path:
    """
    Validate that a path is safe (no path traversal attempts).
    Resolves to absolute path and checks containment if allowed_parent specified.
    
    Args:
        path_str: The path to validate.
        allowed_parent: Optional parent directory that path must be under.
    
    Returns:
        Validated Path object.
    
    Raises:
        ValueError: If path contains traversal attempts or is outside allowed parent.
    """
    path = Path(path_str).resolve()
    
    # Check for attempts to use ".." in the original string
    if ".." in str(path_str):
        raise ValueError(f"Path traversal detected: {path_str}")
    
    # Check containment if allowed_parent specified
    if allowed_parent:
        allowed = Path(allowed_parent).resolve()
        try:
            path.relative_to(allowed)
        except ValueError:
            raise ValueError(
                f"Path {path} is outside allowed parent directory {allowed}"
            )
    
    return path


# --- Output Sanitization ---

SENSITIVE_PATTERNS = [
    (r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[^'\"|\s]+", "REDACTED_API_KEY"),
    (r"password['\"]?\s*[:=]\s*['\"]?[^'\"|\s]+", "REDACTED_PASSWORD"),
    (r"token['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9._\-]+", "REDACTED_TOKEN"),
    (r"secret['\"]?\s*[:=]\s*['\"]?[^'\"|\s]+", "REDACTED_SECRET"),
    (r"authorization['\"]?\s*[:=]\s*['\"]?Bearer\s+[a-zA-Z0-9._\-]+", "REDACTED_AUTH"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}", "REDACTED_EMAIL"),
]


def sanitize_output(text: str, redact_secrets: bool = True) -> str:
    """
    Sanitize output by redacting sensitive data patterns.
    
    Args:
        text: The text to sanitize.
        redact_secrets: Whether to redact API keys, passwords, tokens, etc.
    
    Returns:
        Sanitized text with sensitive data redacted.
    """
    if not redact_secrets:
        return text
    
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    
    return sanitized


# --- Logging Initialization ---

def setup_logging(verbose: bool = True, log_level: str = "INFO") -> logging.Logger:
    """
    Initialize logging with standard configuration.
    
    Args:
        verbose: If True, enables debug logging.
        log_level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR").
    
    Returns:
        Configured logger instance.
    """
    level = logging.DEBUG if verbose else getattr(logging, log_level, logging.INFO)
    
    logger = logging.getLogger("secure_ai_coder")
    if not logger.handlers:  # Avoid duplicate handlers
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    logger.setLevel(level)
    return logger
