"""
app.py
------
Flask web server for the Secure AI Coding Assistant.

Wires the full CrewAI pipeline (main.py) to the web dashboard.
Falls back to a lightweight direct-LLM pipeline if CrewAI is unavailable
(e.g. first deploy before crewai is installed).

Endpoints:
  GET  /              → serve dashboard
  GET  /api/health    → liveness + model info
  POST /api/run       → full pipeline (blocking)
  POST /api/stream    → full pipeline with SSE live updates
"""

from flask import Flask, request, jsonify, send_file, Response, stream_with_context
from dotenv import load_dotenv
import os
import json
import time
import threading
from datetime import datetime

load_dotenv()
app = Flask(__name__)

# ---------------------------------------------------------------------------
# Rate limiting (simple in-memory, per IP)
# ---------------------------------------------------------------------------

from collections import defaultdict

_rate_store = defaultdict(list)   # ip → [timestamp, ...]
RATE_LIMIT   = int(os.getenv("RATE_LIMIT", "10"))       # requests
RATE_WINDOW  = int(os.getenv("RATE_WINDOW", "60"))      # seconds
_rate_lock   = threading.Lock()


def _check_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    with _rate_lock:
        # Purge old timestamps
        _rate_store[ip] = [t for t in _rate_store[ip] if now - t < RATE_WINDOW]
        if len(_rate_store[ip]) >= RATE_LIMIT:
            return False
        _rate_store[ip].append(now)
        return True


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = ALLOWED_ORIGINS
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/run",    methods=["OPTIONS"])
@app.route("/api/stream", methods=["OPTIONS"])
def options_handler():
    return "", 204


# ---------------------------------------------------------------------------
# LLM clients — singleton, initialised once at startup
# ---------------------------------------------------------------------------

_llm_type   = None
_llm_client = None


def _init_client():
    global _llm_type, _llm_client
    if _llm_client is not None:
        return _llm_type, _llm_client

    groq_key      = os.getenv("GROQ_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if groq_key:
        from groq import Groq
        _llm_type   = "groq"
        _llm_client = Groq(api_key=groq_key)
    elif anthropic_key:
        import anthropic
        _llm_type   = "anthropic"
        _llm_client = anthropic.Anthropic(api_key=anthropic_key)
    else:
        raise EnvironmentError("No API key found. Set GROQ_API_KEY or ANTHROPIC_API_KEY.")

    return _llm_type, _llm_client


def _call_llm(client_type, client, prompt, max_tokens=3000):
    if client_type == "groq":
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.1,
        )
        return resp.choices[0].message.content
    else:
        resp = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text


# ---------------------------------------------------------------------------
# Pipeline — try CrewAI first, fall back to direct LLM
# ---------------------------------------------------------------------------

def _active_model_label():
    groq_key = os.getenv("GROQ_API_KEY")
    return "groq/llama-3.3-70b" if groq_key else "anthropic/claude-3-5-sonnet"


def run_pipeline(user_request: str, language: str = "python",
                 progress_cb=None) -> dict:
    """
    Execute the security pipeline.

    Tries the full CrewAI pipeline (main.py) first.
    Falls back to the lightweight direct-LLM chain if CrewAI is not installed.

    progress_cb: optional callable(stage, status, detail) for SSE streaming.
    """
    def _emit(stage, status, detail=""):
        if progress_cb:
            progress_cb(stage, status, detail)

    # ── Try CrewAI pipeline ──────────────────────────────────────────────
    try:
        import sys, os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from main import run_pipeline as crewai_pipeline

        _emit("builder", "running", "Generating secure code…")
        result = crewai_pipeline(
            user_request=user_request,
            language=language,
            max_iterations=3,
            verbose=False,
        )

        # Normalise keys and verdict to what the dashboard expects
        verdict = str(result.get("final_verdict", "ESCALATED")).upper()
        if verdict not in ("APPROVED", "ESCALATED"):
            verdict = "ESCALATED"

        _emit("hacker",  "done", "Vulnerability scan complete")
        _emit("auditor", "done", f"Verdict: {verdict}")

        return {
            "final_verdict":   verdict,
            "iterations":      result.get("iterations", 1),
            "active_llm":      _active_model_label(),
            "builder_output":  str(result.get("builder_output", "")),
            "hacker_report":   str(result.get("hacker_report", "")),
            "auditor_verdict": str(result.get("auditor_verdict", "")),
            "remediation_brief": str(result.get("remediation_brief", "")),
            "session_id":      result.get("session_id", ""),
            "pipeline":        "crewai",
        }

    except ImportError:
        # CrewAI not installed — use lightweight fallback
        pass
    except Exception as e:
        print(f"[app] CrewAI pipeline error: {e} — falling back to direct LLM")

    # ── Fallback: direct LLM 3-agent chain ──────────────────────────────
    client_type, client = _init_client()
    print(f"[app] Fallback pipeline using: {client_type}")

    from Prompts.system_prompts import (
        BUILDER_SYSTEM_PROMPT,
        HACKER_SYSTEM_PROMPT,
        AUDITOR_SYSTEM_PROMPT,
    )

    _emit("builder", "running", f"Generating {language} code…")
    builder_output = _call_llm(client_type, client,
        f"{BUILDER_SYSTEM_PROMPT}\n\n"
        f"Write secure, production-grade {language} code for: {user_request}\n"
        f"Follow your output format: DESIGN RATIONALE → CODE BLOCK → DEPENDENCIES → KNOWN LIMITATIONS.",
        max_tokens=3000,
    )

    _emit("hacker", "running", "Scanning for vulnerabilities…")
    hacker_report = _call_llm(client_type, client,
        f"{HACKER_SYSTEM_PROMPT}\n\n"
        f"Perform a full security review of this {language} code:\n\n{builder_output}\n\n"
        f"Output a Red Team Report in your exact format.",
        max_tokens=2000,
    )

    _emit("auditor", "running", "Issuing verdict…")
    auditor_response = _call_llm(client_type, client,
        f"{AUDITOR_SYSTEM_PROMPT}\n\n"
        f"Red Team Report:\n{hacker_report}\n\n"
        f"Issue your verdict. Start your response with exactly: Verdict: APPROVED or Verdict: ESCALATED",
        max_tokens=1500,
    )

    # Reliable verdict parse — look for the structured prefix first
    verdict = "ESCALATED"
    for line in auditor_response.splitlines():
        if line.strip().upper().startswith("VERDICT:"):
            token = line.split(":", 1)[1].strip().upper()
            if "APPROVED" in token:
                verdict = "APPROVED"
            break
    else:
        if "APPROVED" in auditor_response.upper() and "ESCALATED" not in auditor_response.upper():
            verdict = "APPROVED"

    _emit("auditor", "done", f"Verdict: {verdict}")

    return {
        "final_verdict":   verdict,
        "iterations":      1,
        "active_llm":      client_type,
        "builder_output":  builder_output,
        "hacker_report":   hacker_report,
        "auditor_verdict": auditor_response,
        "remediation_brief": "",
        "session_id":      datetime.now().strftime("%Y%m%d_%H%M%S"),
        "pipeline":        "fallback",
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return send_file("output/dashboard.html")


@app.route("/api/health")
def health():
    crewai_available = False
    try:
        import crewai  # noqa: F401
        crewai_available = True
    except ImportError:
        pass

    return jsonify({
        "status":          "online",
        "anthropic":       bool(os.getenv("ANTHROPIC_API_KEY")),
        "groq":            bool(os.getenv("GROQ_API_KEY")),
        "active_model":    _active_model_label(),
        "crewai":          crewai_available,
        "pipeline":        "crewai" if crewai_available else "fallback",
        "version":         "2.0.0",
    })


@app.route("/api/run", methods=["POST"])
def run():
    """Blocking pipeline endpoint — returns when all agents are done."""
    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip):
        return jsonify({
            "status":  "error",
            "message": f"Rate limit exceeded. Max {RATE_LIMIT} requests per {RATE_WINDOW}s.",
        }), 429

    data = request.json
    if not data or not data.get("request"):
        return jsonify({"status": "error", "message": "request field required"}), 400

    user_request = data["request"].strip()
    language     = data.get("language", "python").lower()

    if len(user_request) > 5000:
        return jsonify({"status": "error", "message": "Request too long (max 5000 chars)"}), 400

    valid_languages = {"python", "javascript", "go", "rust"}
    if language not in valid_languages:
        return jsonify({"status": "error", "message": f"Language must be one of: {', '.join(valid_languages)}"}), 400

    try:
        result = run_pipeline(user_request, language)
        return jsonify({"status": "success", **result})
    except Exception as e:
        print(f"[app] Pipeline error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/stream", methods=["POST"])
def stream():
    """
    SSE streaming endpoint — emits live stage updates as the pipeline runs.
    
    Event format:
        data: {"stage": "builder"|"hacker"|"auditor"|"done"|"error",
                "status": "running"|"done"|"error",
                "detail": "...",
                "result": {...}}   ← only on final "done" event
    """
    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip):
        def _deny():
            msg = json.dumps({"stage": "error", "status": "error",
                              "detail": "Rate limit exceeded."})
            yield f"data: {msg}\n\n"
        return Response(stream_with_context(_deny()), mimetype="text/event-stream")

    data = request.json
    if not data or not data.get("request"):
        def _bad():
            yield f"data: {json.dumps({'stage':'error','status':'error','detail':'request field required'})}\n\n"
        return Response(stream_with_context(_bad()), mimetype="text/event-stream")

    user_request = data["request"].strip()[:5000]
    language     = data.get("language", "python").lower()

    # Collect pipeline result + events via a shared queue
    import queue
    event_queue = queue.Queue()
    pipeline_result = {}

    def _progress(stage, status, detail=""):
        event_queue.put({"stage": stage, "status": status, "detail": detail})

    def _run_pipeline_thread():
        try:
            result = run_pipeline(user_request, language, progress_cb=_progress)
            pipeline_result.update(result)
            event_queue.put({"stage": "done", "status": "done",
                             "detail": "Pipeline complete", "result": result})
        except Exception as e:
            event_queue.put({"stage": "error", "status": "error", "detail": str(e)})

    t = threading.Thread(target=_run_pipeline_thread, daemon=True)
    t.start()

    def _generate():
        # Heartbeat so the connection doesn't time out on slow deploys
        yield ": heartbeat\n\n"
        while True:
            try:
                event = event_queue.get(timeout=120)
                yield f"data: {json.dumps(event)}\n\n"
                if event["stage"] in ("done", "error"):
                    break
            except queue.Empty:
                yield ": heartbeat\n\n"

    return Response(
        stream_with_context(_generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",    # disable Nginx buffering on Render
        },
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)