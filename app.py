from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
from collections import defaultdict
import threading, time, os

from security_utils import (
    BLOCKED_REQUEST_MESSAGE,
    check_malicious_request,
    generate_secure_session_id,
)

load_dotenv()
app = Flask(__name__)

SUPPORTED_LANGUAGES = {"python", "javascript", "go", "rust"}
MAX_RUN_REQUEST_LENGTH = 2000
MAX_SCAN_CODE_LENGTH = 50000

_rate_store = defaultdict(list)
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "10"))
RATE_WINDOW = int(os.getenv("RATE_WINDOW", "60"))
_rate_lock = threading.Lock()

def check_rate(ip):
    now = time.time()
    with _rate_lock:
        _rate_store[ip] = [t for t in _rate_store[ip] if now - t < RATE_WINDOW]
        if len(_rate_store[ip]) >= RATE_LIMIT:
            return False
        _rate_store[ip].append(now)
        return True

@app.after_request
def add_cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r

@app.route("/api/run", methods=["OPTIONS"])
@app.route("/api/scan", methods=["OPTIONS"])
def options():
    return "", 204

_llm_type = None
_llm_client = None

def get_client():
    global _llm_type, _llm_client
    if _llm_client:
        return _llm_type, _llm_client
    groq_key = os.getenv("GROQ_API_KEY")
    anth_key = os.getenv("ANTHROPIC_API_KEY")
    if groq_key:
        from groq import Groq
        _llm_type, _llm_client = "groq", Groq(api_key=groq_key)
    elif anth_key:
        import anthropic
        _llm_type, _llm_client = "anthropic", anthropic.Anthropic(api_key=anth_key)
    else:
        raise EnvironmentError("No API key found.")
    return _llm_type, _llm_client

def call_llm(ct, client, prompt, max_tokens=1000):
    if ct == "groq":
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.1)
        return r.choices[0].message.content
    r = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}])
    return r.content[0].text


def parse_verdict(auditor_response: str) -> str:
    for line in auditor_response.splitlines():
        if line.strip().upper().startswith("VERDICT:"):
            return "APPROVED" if "APPROVED" in line.upper() else "ESCALATED"
    return "ESCALATED"


def run_scan(code: str, language: str = "python"):
    """Scan existing source code — Hacker + static analysis + Auditor (no Builder)."""
    from Prompts.system_prompts import HACKER_SYSTEM_PROMPT, AUDITOR_SYSTEM_PROMPT
    from tools.static_analysis import run_all_tools

    ct, client = get_client()
    print(f"[scan] using {ct}")

    static_analysis = ""
    if language == "python":
        static_analysis = run_all_tools(code=code, language=language, mock=True)

    hacker_report = call_llm(
        ct,
        client,
        f"{HACKER_SYSTEM_PROMPT}\n\n"
        f"Find vulnerabilities in this {language} code (max 8 findings):\n\n"
        f"```\n{code}\n```\n\n"
        f"Format each as: [CRITICAL/HIGH/MEDIUM/LOW] CWE-XXX: description",
        max_tokens=1000,
    )

    auditor_prompt = (
        f"{AUDITOR_SYSTEM_PROMPT}\n\n"
        f"## CODE UNDER REVIEW:\n```\n{code}\n```\n\n"
        f"## RED TEAM FINDINGS:\n{hacker_report}\n"
    )
    if static_analysis:
        auditor_prompt += f"\n## STATIC ANALYSIS:\n{static_analysis}\n"
    auditor_prompt += "\nStart your response with: Verdict: APPROVED or Verdict: ESCALATED"

    auditor_response = call_llm(ct, client, auditor_prompt, max_tokens=800)

    return {
        "final_verdict": parse_verdict(auditor_response),
        "active_llm": ct,
        "code": code,
        "hacker_report": hacker_report,
        "auditor_verdict": auditor_response,
        "static_analysis": static_analysis or None,
        "session_id": generate_secure_session_id(),
        "pipeline": "scan",
    }


def run_pipeline(user_request, language="python"):
    from Prompts.system_prompts import BUILDER_SYSTEM_PROMPT, HACKER_SYSTEM_PROMPT, AUDITOR_SYSTEM_PROMPT
    ct, client = get_client()
    print(f"[pipeline] using {ct}")

    builder_output = call_llm(ct, client,
        f"{BUILDER_SYSTEM_PROMPT}\n\nWrite secure {language} code for: {user_request}\nBe concise. Return code with security comments.",
        max_tokens=1200)

    hacker_report = call_llm(ct, client,
        f"{HACKER_SYSTEM_PROMPT}\n\nFind vulnerabilities in this {language} code (max 6 findings):\n\n{builder_output}\n\nFormat each as: [CRITICAL/HIGH/MEDIUM/LOW] CWE-XXX: description",
        max_tokens=800)

    auditor_response = call_llm(ct, client,
        f"{AUDITOR_SYSTEM_PROMPT}\n\nFindings:\n{hacker_report}\n\nStart your response with: Verdict: APPROVED or Verdict: ESCALATED",
        max_tokens=600)

    return {
        "final_verdict": parse_verdict(auditor_response),
        "iterations": 1,
        "active_llm": ct,
        "builder_output": builder_output,
        "hacker_report": hacker_report,
        "auditor_verdict": auditor_response,
        "session_id": generate_secure_session_id(),
        "pipeline": "direct",
    }

@app.route("/")
def home():
    return send_file("output/dashboard.html")

@app.route("/api/health")
def health():
    return jsonify({
        "status": "online",
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "active_model": "groq/llama-3.3-70b" if os.getenv("GROQ_API_KEY") else "anthropic/claude-3-5-sonnet",
        "version": "2.1.0",
        "endpoints": ["/api/run", "/api/scan", "/api/health"],
    })


def _rate_limited():
    ip = request.remote_addr or "unknown"
    if not check_rate(ip):
        return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429
    return None


def _validate_language(lang: str):
    if lang not in SUPPORTED_LANGUAGES:
        return jsonify({"status": "error", "message": "Invalid language"}), 400
    return None


@app.route("/api/run", methods=["POST"])
def run():
    blocked = _rate_limited()
    if blocked:
        return blocked

    data = request.json
    if not data or not data.get("request"):
        return jsonify({"status": "error", "message": "request field required"}), 400

    req = data["request"].strip()
    if len(req) > MAX_RUN_REQUEST_LENGTH:
        return jsonify({"status": "error", "message": "Request too long"}), 400

    filter_result = check_malicious_request(req)
    if filter_result.blocked:
        return jsonify({
            "status": "blocked",
            "message": BLOCKED_REQUEST_MESSAGE,
            "category": filter_result.category,
        }), 403

    lang = data.get("language", "python").lower()
    lang_error = _validate_language(lang)
    if lang_error:
        return lang_error

    try:
        result = run_pipeline(req, lang)
        return jsonify({"status": "success", **result})
    except Exception as e:
        print(f"[error] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/scan", methods=["POST"])
def scan():
    blocked = _rate_limited()
    if blocked:
        return blocked

    data = request.json
    if not data or not data.get("code"):
        return jsonify({"status": "error", "message": "code field required"}), 400

    code = data["code"].strip()
    if not code:
        return jsonify({"status": "error", "message": "code field required"}), 400
    if len(code) > MAX_SCAN_CODE_LENGTH:
        return jsonify({"status": "error", "message": "Code too long"}), 400

    lang = data.get("language", "python").lower()
    lang_error = _validate_language(lang)
    if lang_error:
        return lang_error

    try:
        result = run_scan(code, lang)
        return jsonify({"status": "success", **result})
    except Exception as e:
        print(f"[error] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)