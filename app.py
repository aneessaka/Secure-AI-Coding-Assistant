from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
import anthropic
import os

load_dotenv()
app = Flask(__name__)

def run_pipeline(user_request, language="python"):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Builder Agent
    builder = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": f"Write secure {language} code for: {user_request}. Include security best practices."}]
    )
    builder_output = builder.content[0].text

    # Hacker Agent
    hacker = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": f"You are a security expert. Find vulnerabilities in this code:\n{builder_output}\nList findings as CRITICAL/HIGH/MEDIUM/LOW with CWE numbers."}]
    )
    hacker_report = hacker.content[0].text

    # Auditor Agent
    auditor = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": f"Based on these findings:\n{hacker_report}\nVerdict: reply with APPROVED if code is safe, ESCALATED if it needs fixes."}]
    )
    verdict = "APPROVED" if "APPROVED" in auditor.content[0].text.upper() else "ESCALATED"

    return {
        "final_verdict": verdict,
        "iterations": 1,
        "builder_output": builder_output,
        "hacker_report": hacker_report,
        "auditor_verdict": auditor.content[0].text,
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
        "active_model": "claude-sonnet-4-20250514",
        "version": "1.0.0"
    })

@app.route("/api/run", methods=["POST"])
def run():
    try:
        data = request.json
        if not data or not data.get("request"):
            return jsonify({"status": "error", "message": "request field required"}), 400
        result = run_pipeline(data["request"], data.get("language", "python"))
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
