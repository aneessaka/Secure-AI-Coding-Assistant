"""
Flask backend API for Secure AI Coding Assistant
Provides REST endpoints for the dashboard and CLI
"""

from flask import Flask, request, jsonify, send_file
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Import pipeline
from main import run_pipeline

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max

@app.route("/", methods=["GET"])
def home():
    """Serve the dashboard"""
    try:
        return send_file("output/dashboard.html")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint"""
    groq_active = bool(os.getenv("GROQ_API_KEY"))
    anthropic_active = bool(os.getenv("ANTHROPIC_API_KEY"))

    active_model = "anthropic/claude-sonnet-4" if anthropic_active else (
        "groq/llama-3.3-70b" if groq_active else "none"
    )

    return jsonify({
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "groq_key_present": groq_active,
        "anthropic_key_present": anthropic_active,
        "active_model": active_model,
        "version": "1.0.0",
    })

@app.route("/api/run", methods=["POST"])
def run():
    """Execute the security review pipeline"""
    try:
        data = request.json

        # Validate request
        if not data or not data.get("request"):
            return jsonify({
                "status": "error",
                "message": "Missing 'request' field in JSON body"
            }), 400

        user_request = data.get("request", "").strip()
        if not user_request or len(user_request) > 5000:
            return jsonify({
                "status": "error",
                "message": "Request must be 1-5000 characters"
            }), 400

        language = data.get("language", "python").lower()
        if language not in ["python", "rust", "javascript", "go"]:
            return jsonify({
                "status": "error",
                "message": "Language must be: python, rust, javascript, or go"
            }), 400

        max_iterations = min(int(data.get("iterations", 3)), 5)

        # Run pipeline
        result = run_pipeline(
            user_request=user_request,
            language=language,
            max_iterations=max_iterations,
            verbose=False,
        )

        return jsonify({
            "status": "success",
            "verdict": result.get("final_verdict", "UNKNOWN").upper(),
            "iterations": result.get("iterations", 0),
            "builder_output": result.get("builder_output", ""),
            "hacker_report": result.get("hacker_report", ""),
            "auditor_verdict": result.get("auditor_verdict", ""),
            "session_id": result.get("session_id", ""),
            "timestamp": result.get("timestamp", ""),
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route("/api/models", methods=["GET"])
def models():
    """List available models"""
    return jsonify({
        "models": [
            {
                "id": "anthropic/claude-sonnet-4",
                "name": "Claude Sonnet 4 (Recommended)",
                "provider": "Anthropic",
                "status": "active" if os.getenv("ANTHROPIC_API_KEY") else "offline",
            },
            {
                "id": "groq/llama-3.3-70b",
                "name": "Llama 3.3 70B (Fast)",
                "provider": "Groq",
                "status": "active" if os.getenv("GROQ_API_KEY") else "offline",
            }
        ]
    })

@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Internal server error"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    print(f"Starting Secure AI Coding Assistant API")
    print(f"Listening on http://localhost:{port}")
    print(f"Dashboard: http://localhost:{port}/")
    print(f"API Docs: http://localhost:{port}/api/health")
    print()

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=False,
    )
