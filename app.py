from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
import os

load_dotenv()
app = Flask(__name__)

def get_client():
    groq_key = os.getenv("GROQ_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    
    if groq_key:
        from groq import Groq
        return "groq", Groq(api_key=groq_key)
    elif anthropic_key:
        import anthropic
        return "anthropic", anthropic.Anthropic(api_key=anthropic_key)
    else:
        raise EnvironmentError("No API key found")

def call_llm(client_type, client, prompt):
    if client_type == "groq":
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.1
        )
        return response.choices[0].message.content
    else:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

def run_pipeline(user_request, language="python"):
    client_type, client = get_client()
    print(f"Using: {client_type}")

    # Builder Agent
    builder_output = call_llm(client_type, client,
        f"You are a senior {language} developer. Write secure, production-grade {language} code for: {user_request}. "
        f"Include input validation, error handling, and security best practices. Return only the code with comments."
    )

    # Hacker Agent
    hacker_report = call_llm(client_type, client,
        f"You are a security penetration tester. Analyze this {language} code for vulnerabilities:\n\n{builder_output}\n\n"
        f"List each finding as: [CRITICAL/HIGH/MEDIUM/LOW] CWE-XXX: Description. Be specific and technical."
    )

    # Auditor Agent
    auditor_response = call_llm(client_type, client,
        f"You are a security auditor. Based on these findings:\n\n{hacker_report}\n\n"
        f"Reply with exactly one word: APPROVED if the code is safe enough, ESCALATED if it needs fixes."
    )

    verdict = "APPROVED" if "APPROVED" in auditor_response.upper() else "ESCALATED"

    return {
        "final_verdict": verdict,
        "iterations": 1,
        "active_llm": client_type,
        "builder_output": builder_output,
        "hacker_report": hacker_report,
        "auditor_verdict": auditor_response,
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
        "active_model": "groq/llama-3.3-70b (primary)" if os.getenv("GROQ_API_KEY") else "anthropic/claude-3-5-sonnet",
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
