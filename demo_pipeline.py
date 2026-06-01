#!/usr/bin/env python
"""
demo_pipeline.py
-----------------
Demonstration of the Secure AI Coding Assistant pipeline
using mock outputs to showcase the workflow without full
agent execution (since CrewAI requires special LLM adapters).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

def simulate_pipeline():
    """Run a simulated pipeline demonstration"""

    print("\n" + "="*70)
    print("[DEMO] SECURE AI CODING ASSISTANT - PIPELINE DEMONSTRATION")
    print("="*70)

    user_request = "Build a secure user authentication system with JWT tokens"
    language = "python"

    print(f"\nUser Request: {user_request}")
    print(f"Language: {language}")
    print(f"Started: {datetime.now().isoformat()}")
    print()

    # Mock iteration 1
    print(f"\n{''*70}")
    print("ITERATION 1/3")
    print(f"{''*70}\n")

    print("[1]   BUILDER — Generating code...")
    builder_output_1 = """
## DESIGN RATIONALE
We implement JWT-based authentication using industry standards:
- Symmetric HS256 for signing (can upgrade to RS256 with key rotation)
- 1-hour token expiration with refresh token mechanism
- Secure password hashing using bcrypt (12 rounds)
- Input validation on all API endpoints

## CODE BLOCK
```python
import jwt
import bcrypt
import hashlib
from datetime import datetime, timedelta

class AuthenticationService:
    SECRET_KEY = "your-secret-key-here"

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12))

    @staticmethod
    def verify_password(password: str, hash_val: str) -> bool:
        return bcrypt.checkpw(password.encode(), hash_val)

    @classmethod
    def create_token(cls, user_id: str) -> str:
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(hours=1),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, cls.SECRET_KEY, algorithm='HS256')

    @classmethod
    def verify_token(cls, token: str) -> dict:
        try:
            return jwt.decode(token, cls.SECRET_KEY, algorithms=['HS256'])
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
```

## DEPENDENCIES
- PyJWT>=2.8.0
- bcrypt>=4.1.0

## KNOWN LIMITATIONS
- Secret key should be loaded from environment (not hardcoded)
- Refresh token rotation not fully implemented
- Rate limiting should be added at API gateway level
"""
    print(" Builder output received (1247 chars)")

    print("\n[1]  RED TEAM HACKER — Attacking code...")
    hacker_report_1 = """
## RED TEAM ATTACK REPORT — ITERATION 1

### VERDICT: HIGH_FAIL

### CRITICAL FINDINGS

1. **Hardcoded Secret Key**
   - Severity: CRITICAL | CWE-798
   - Location: class property SECRET_KEY
   - Description: Secret is hardcoded in source code
   - Attack: Attacker with source access gains signing capability
   - PoC: Can forge arbitrary JWT tokens
   - Fix: Load from environment variable

2. **Weak Token Expiration**
   - Severity: HIGH | CWE-613
   - Location: timedelta(hours=1)
   - Description: 1-hour expiration is too long for sensitive operations
   - Attack: Stolen tokens remain valid for extended period
   - Fix: Reduce to 15 minutes, use refresh tokens

3. **No HTTPS Enforcement Evident**
   - Severity: HIGH | CWE-295
   - Description: No indication of TLS requirement in code
   - Attack: Tokens transmitted over HTTP can be intercepted
   - Fix: Document HTTPS-only requirement

### SUMMARY
- Total Findings: 3
- Critical: 1 | High: 2 | Medium: 0 | Low: 0
- Exploitability: HIGH
- Risk Assessment: Code cannot be approved without fixes
"""
    print(" Hacker report received (987 chars, HIGH severity found)")

    print("\n[1]  SECURITY AUDITOR — Issuing verdict...")
    auditor_verdict_1 = """
## SECURITY AUDITOR VERDICT — ITERATION 1

### VERDICT: ESCALATED 

### STATIC ANALYSIS RESULTS
- AST Security Check: FAIL (Hardcoded secret detected)
- Tool Report: 3 CRITICAL issues identified

### SYNTHESIS
After reviewing both the Red Team Report and static analysis:

**Critical Issues Found:**
1. Hardcoded SECRET_KEY (CWE-798) — MUST FIX
2. Weak token expiration (CWE-613) — MUST FIX
3. No HTTPS indication (CWE-295) — MUST FIX

**Status:** Code cannot be approved for production use.

### REMEDIATION BRIEF FOR ITERATION 2

1. **Load SECRET_KEY from environment:**
   ```python
   import os
   SECRET_KEY = os.environ.get('JWT_SECRET')
   if not SECRET_KEY:
       raise ValueError("JWT_SECRET not set")
   ```

2. **Reduce token expiration to 15 minutes:**
   ```python
   'exp': datetime.utcnow() + timedelta(minutes=15)
   ```

3. **Add documentation requiring HTTPS:**
   ```
   Add comment: "This service MUST be deployed with HTTPS-only enforcement"
   ```

4. **Implement refresh token mechanism:**
   - Add refresh_token endpoint
   - Validate refresh tokens server-side

**Confidence:** High
**Next Step:** Retry with builder applying these fixes
"""
    print(" Auditor verdict received")

    print(f"\n✅ ITERATION 1 VERDICT: ESCALATED")
    print(" Code NEEDS REMEDIATION — retrying...")

    # Mock iteration 2
    print(f"\n{''*70}")
    print("ITERATION 2/3")
    print(f"{''*70}\n")

    print("[2]   BUILDER — Applying fixes...")
    builder_output_2 = """
## DESIGN RATIONALE (REVISED)
Addressed all critical findings from iteration 1:
- SECRET_KEY now loaded from environment with validation
- Token expiration reduced to 15 minutes for enhanced security
- Added HTTPS enforcement documentation
- Implemented refresh token mechanism for session continuity

## CODE BLOCK
```python
import jwt
import bcrypt
import os
from datetime import datetime, timedelta
from typing import Dict

class AuthenticationService:
    SECRET_KEY = os.environ.get('JWT_SECRET')
    REFRESH_SECRET = os.environ.get('JWT_REFRESH_SECRET')

    def __init__(self):
        if not self.SECRET_KEY or not self.REFRESH_SECRET:
            raise ValueError("JWT_SECRET and JWT_REFRESH_SECRET must be set")

    @staticmethod
    def hash_password(password: str) -> str:
        salt = bcrypt.gensalt(12)
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    def verify_password(password: str, hash_val: str) -> bool:
        return bcrypt.checkpw(password.encode(), hash_val.encode())

    @classmethod
    def create_tokens(cls, user_id: str) -> Dict[str, str]:
        now = datetime.utcnow()
        access_payload = {
            'user_id': user_id,
            'token_type': 'access',
            'exp': now + timedelta(minutes=15),
            'iat': now
        }
        refresh_payload = {
            'user_id': user_id,
            'token_type': 'refresh',
            'exp': now + timedelta(days=7),
            'iat': now
        }
        return {
            'access_token': jwt.encode(access_payload, cls.SECRET_KEY, algorithm='HS256'),
            'refresh_token': jwt.encode(refresh_payload, cls.REFRESH_SECRET, algorithm='HS256')
        }

    @classmethod
    def verify_access_token(cls, token: str) -> Dict:
        try:
            return jwt.decode(token, cls.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
```

## DEPENDENCIES
- PyJWT>=2.8.0
- bcrypt>=4.1.0
- python-dotenv>=0.19.0

## KNOWN LIMITATIONS
- Requires environment variables JWT_SECRET and JWT_REFRESH_SECRET (32+ bytes)
- Refresh token blacklisting not implemented (can be added)
- Should be deployed with HTTPS-only enforcement
"""
    print(" Builder output received with fixes (1823 chars)")

    print("\n[2]  RED TEAM HACKER — Reviewing fixes...")
    hacker_report_2 = """
## RED TEAM ATTACK REPORT — ITERATION 2

### VERDICT: PASS 

### ANALYSIS
Previous critical issues have been properly remediated:

 SECRET_KEY now loaded from environment (CWE-798 FIXED)
 Token expiration reduced to 15 minutes (CWE-613 FIXED)
 HTTPS requirement documented (CWE-295 FIXED)
 Refresh token mechanism implemented correctly

### NEW SECURITY OBSERVATIONS
- Strong bcrypt implementation (12 rounds, good)
- Proper JWT claims structure (token_type discrimination)
- Error handling is appropriate (generic exceptions)
- No SQL injection vectors (no database queries shown)

### FINDINGS: NONE

### SUMMARY
- Total Findings: 0
- Risk Assessment: LOW
- Exploitability: N/A
- Code Quality: GOOD

### CONCLUSION
Code has been substantially improved. All critical issues resolved. Ready for final audit.
"""
    print(" Hacker report received (no critical findings)")

    print("\n[2]  SECURITY AUDITOR — Final verdict...")
    auditor_verdict_2 = """
## SECURITY AUDITOR FINAL VERDICT — ITERATION 2

### VERDICT: APPROVED 

### STATIC ANALYSIS RESULTS
- AST Security Check: PASS
- Hardcoded Secrets: NOT FOUND
- CWE-798 Status: RESOLVED
- Overall Status: CLEAN

### SYNTHESIS
After reviewing the revised code:

**Red Team Report:** PASS (no findings)
**Static Analysis:** PASS (clean)
**Code Quality:** GOOD

The application now meets production security standards.

**Approved For:**
 Production deployment
 Security compliance review
 Public code repository

**Deployment Requirements:**
1. Set environment variables (JWT_SECRET, JWT_REFRESH_SECRET)
2. Deploy with HTTPS-only enforcement
3. Enable security headers (HSTS, CSP, etc.)
4. Monitor authentication endpoints for anomalies

**Confidence:** Very High
**Approval Status:** APPROVED

---
*Generated by Secure AI Coding Assistant*
*All static analysis tools passed*
*Red Team: No exploitable vulnerabilities found*
"""
    print(" Auditor verdict received")

    print(f"\n✅ ITERATION 2 VERDICT: APPROVED")
    print(" Code APPROVED on iteration 2!")

    # Report generation
    print(f"\n{''*70}")
    print(" WRITING AUDIT REPORTS")
    print(f"{''*70}\n")

    audit_result = {
        "timestamp": datetime.now().isoformat(),
        "user_request": user_request,
        "language": language,
        "iterations": 2,
        "final_verdict": "approved",
        "builder_output_iteration_1": builder_output_1,
        "hacker_report_iteration_1": hacker_report_1,
        "auditor_verdict_iteration_1": auditor_verdict_1,
        "builder_output_iteration_2": builder_output_2,
        "hacker_report_iteration_2": hacker_report_2,
        "auditor_verdict_iteration_2": auditor_verdict_2,
    }

    # Save JSON report
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"session_{session_id}.json"

    with open(json_path, "w") as f:
        json.dump(audit_result, f, indent=2)

    print(f" JSON report: {json_path}")

    # Save markdown report
    md_path = output_dir / f"session_{session_id}_report.md"
    md_content = f"""# Security Audit Report

| Field | Value |
|-------|-------|
| Session ID | `{session_id}` |
| Outcome | **✅ APPROVED** |
| Timestamp | {audit_result['timestamp']} |
| Language | PYTHON |
| Iterations | 2/3 |
| User Request | {user_request} |

---

## Executive Summary

The JWT-based authentication system has been **APPROVED** for production deployment after 2 iterations of review and remediation.

**Final Verdict:** APPROVED 

**Security Assessment:** LOW RISK

---

## Iteration History

### Iteration 1: Initial Build

#### 🔨 Builder Output
Generated secure JWT authentication system with bcrypt password hashing and JWT token management.

#### 💀 Red Team Report
Found 3 critical issues:
1. Hardcoded SECRET_KEY
2. Weak token expiration (1 hour)
3. No HTTPS enforcement

**Verdict:** HIGH_FAIL

#### ⚖️ Auditor Verdict
**ESCALATED** — Code has critical vulnerabilities requiring fixes

---

### Iteration 2: Remediation Applied

#### 🔨 Builder Output
Applied all remediation fixes:
- Loaded SECRET_KEY from environment
- Reduced token expiration to 15 minutes
- Implemented refresh token mechanism
- Added HTTPS requirement documentation

#### 💀 Red Team Report
**PASS** — All issues resolved, no new findings

#### ⚖️ Auditor Verdict
**APPROVED** — Code meets production security standards

---

## Final Approved Code

```python
import jwt
import bcrypt
import os
from datetime import datetime, timedelta
from typing import Dict

class AuthenticationService:
    SECRET_KEY = os.environ.get('JWT_SECRET')
    REFRESH_SECRET = os.environ.get('JWT_REFRESH_SECRET')

    def __init__(self):
        if not self.SECRET_KEY or not self.REFRESH_SECRET:
            raise ValueError("JWT_SECRET and JWT_REFRESH_SECRET must be set")

    @staticmethod
    def hash_password(password: str) -> str:
        salt = bcrypt.gensalt(12)
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    def verify_password(password: str, hash_val: str) -> bool:
        return bcrypt.checkpw(password.encode(), hash_val.encode())

    @classmethod
    def create_tokens(cls, user_id: str) -> Dict[str, str]:
        now = datetime.utcnow()
        access_payload = {{
            'user_id': user_id,
            'token_type': 'access',
            'exp': now + timedelta(minutes=15),
            'iat': now
        }}
        refresh_payload = {{
            'user_id': user_id,
            'token_type': 'refresh',
            'exp': now + timedelta(days=7),
            'iat': now
        }}
        return {{
            'access_token': jwt.encode(access_payload, cls.SECRET_KEY, algorithm='HS256'),
            'refresh_token': jwt.encode(refresh_payload, cls.REFRESH_SECRET, algorithm='HS256')
        }}

    @classmethod
    def verify_access_token(cls, token: str) -> Dict:
        try:
            return jwt.decode(token, cls.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
```

---

## Deployment Checklist

[OK] Code approved for production
[OK] All security findings resolved
[OK] Static analysis: PASS
[OK] Red Team review: PASS
[OK] No hardcoded secrets
[OK] Environment variables configured
[OK] Refresh token mechanism implemented

---

*Report generated by Secure AI Coding Assistant*
*All automated security checks passed*
*Red Team: Zero exploitable vulnerabilities found*
"""

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f" Markdown report: {md_path}")

    # Final summary
    print(f"\n{'='*70}")
    print("✅ PIPELINE COMPLETE")
    print(f"{'='*70}")
    print(f"Final Verdict: APPROVED")
    print(f"Iterations: 2/3")
    print()

    return audit_result

if __name__ == "__main__":
    result = simulate_pipeline()
    sys.exit(0)
