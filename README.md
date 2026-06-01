# 🔐 Secure AI Coding Assistant
### A Multi-Agent Security Pipeline using LangGraph + CrewAI

> **Master's-level Computer Science Project**  
> Autonomous, secure-by-default code generation with adversarial red-teaming and programmatic static analysis.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER REQUEST (natural language)              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              LANGGRAPH STATE MACHINE (agentic loop)             │
│                                                                 │
│  ┌─────────────────────────────────────────┐                   │
│  │  AGENT 1: THE BUILDER (CrewAI)          │                   │
│  │  Persona: Expert Software Engineer      │                   │
│  │  Defaults: Rust › Go › Python           │                   │
│  │  Tools: None (pure generation)          │                   │
│  └─────────────────┬───────────────────────┘                   │
│                    │ code                                        │
│                    ▼                                            │
│  ┌─────────────────────────────────────────┐                   │
│  │  AGENT 2: THE RED TEAM HACKER (CrewAI)  │                   │
│  │  Persona: ADVERSARY-1                   │                   │
│  │  Task: Attack code · OWASP Top 10       │                   │
│  │  Tools: None (pure LLM reasoning)       │                   │
│  └─────────────────┬───────────────────────┘                   │
│                    │ Red Team Report                            │
│                    ▼                                            │
│  ┌─────────────────────────────────────────┐  ┌─────────────┐  │
│  │  AGENT 3: THE SECURITY AUDITOR (CrewAI) │◄►│ STATIC TOOLS│  │
│  │  Persona: Compliance Officer            │  │ Bandit      │  │
│  │  Task: Synthesize verdict               │  │ AST check   │  │
│  │  Tools: StaticAnalysisTool ✓            │  │ Cargo Audit │  │
│  └─────────────────┬───────────────────────┘  └─────────────┘  │
│                    │                                            │
│                    ▼                                            │
│           ┌────── ROUTER ──────┐                                │
│           │                    │                                │
│     REJECTED              APPROVED                             │
│     iter < 3 ────────►    OUTPUT ✓                             │
│     (loop back)                                                 │
│           │                                                     │
│     ESCALATED (iter=3, critical issues remain)                 │
│     Human review required                                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                    output/session_*.json
                    output/session_*_report.md
```

---

## Project Directory Structure

```
secure_ai_coder/
│
├── main.py                        # 🎯 Entry point — LangGraph orchestration
│
├── agents/
│   ├── __init__.py
│   └── agent_definitions.py       # CrewAI Agent, Task factory functions
│
├── prompts/
│   ├── __init__.py
│   └── system_prompts.py          # Role-locked system prompts (the "constitution")
│
├── tools/
│   ├── __init__.py
│   └── static_analysis.py         # Bandit, AST, Cargo Audit/Clippy wrappers
│
├── config/
│   ├── __init__.py
│   └── settings.py                # Environment-based configuration
│
├── output/
│   ├── __init__.py
│   └── report_writer.py           # JSON + Markdown audit trail generator
│
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py           # Full test suite (14 tests, no LLM needed)
│
├── requirements.txt               # Pinned Python dependencies
├── .env.example                   # Environment variable template
├── .gitignore                     # Excludes secrets and output reports
└── README.md                      # This file
```

---

## Quick Start

### 1. Prerequisites

```bash
# Python 3.11+ required
python --version

# (Optional for real tool mode) Install Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo install cargo-audit

# (Optional for real tool mode) Install Bandit
pip install bandit
```

### 2. Clone and Install

```bash
git clone <your-repo>
cd secure_ai_coder

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
nano .env
```

### 4. Run the Pipeline

```bash
# Interactive mode
python main.py --interactive

# Direct request
python main.py --request "Build a JWT authentication middleware" --language python

# Rust mode
python main.py --request "Write a secure file parser" --language rust
```

---

## The Three Agents — Design Rationale

### Agent 1: The Builder
**Why no tools?** Code generation is a pure synthesis task. Giving the Builder tool access
creates unnecessary attack surface and can distract from clean generation. The Builder's
"tool" is its vast training knowledge about secure coding patterns.

**Why strict language defaults?** Memory safety must be the default, not an option. Rust
eliminates entire classes of vulnerabilities (buffer overflow, use-after-free) at compile
time. The Builder defaults to Rust unless overridden.

### Agent 2: The Red Team Hacker (ADVERSARY-1)
**Why no tools?** The Hacker is pure adversarial reasoning — it must think like a threat
actor. Tool access would constrain it to what tools can find; LLM reasoning can identify
*logical flaws* that no static tool will catch (e.g. IDOR, business logic bypasses,
JWT algorithm confusion).

**Why the "cynical" persona?** Prompt engineering research shows that adopting a strongly
committed adversarial persona reduces LLM "helpfulness bias" — the tendency to be
charitable about code quality. ADVERSARY-1 is constitutionally skeptical.

### Agent 3: The Security Auditor
**Why tools?** The Auditor is the last line of defense. LLM reasoning can hallucinate
"clean" verdicts. Static analysis tools provide *ground truth* — a real Bandit scan
cannot be socially engineered. The combination of LLM + tool is more reliable than either
alone.

**Why the arbitrator role?** Separating "who finds bugs" (Hacker) from "who decides
consequences" (Auditor) mirrors real security organizations. The Auditor brings a
compliance lens: not just "is this vulnerable" but "what is the risk in context?"

---

## The Agentic Loop — State Machine Design

LangGraph manages the loop as an explicit state machine rather than a simple `while` loop
because:

1. **State is explicit and inspectable** — every iteration's outputs are stored in `AgentState`
2. **Edges are typed and validated** — the router's conditional edges prevent undefined transitions
3. **Human-in-the-loop is natural** — adding a pause node for human review requires one `interrupt_before`
4. **Graph is replayable** — any state can be replayed from a checkpoint for debugging

### Adding Human-in-the-Loop

To add a human approval step before the Auditor, modify `build_security_graph()`:

```python
# In main.py, build_security_graph():
compiled_graph = graph.compile(
    interrupt_before=["auditor"]  # Pause here for human review
)

# Then in your application code:
thread = {"configurable": {"thread_id": session_id}}
final_state = compiled_graph.invoke(initial_state, thread)

# System pauses — human can inspect state, modify, then resume:
final_state = compiled_graph.invoke(None, thread)  # Resume
```

---

## Static Analysis Tools — Architecture

The `run_all_tools()` dispatcher follows a fail-safe design:

1. **AST checker always runs** — pure Python, zero dependencies, catches the most critical issues
2. **Bandit runs in mock mode by default** — returns realistic output even without Bandit installed
3. **Cargo tools run in mock mode** — switch to `mock=False` + a real Rust project path for production
4. **All failures are graceful** — a tool that can't run returns a `ToolReport` with `ran_successfully=False`
   and the Auditor is instructed to flag this explicitly in its verdict

To enable real tool execution:
```bash
# In .env:
USE_MOCK_TOOLS=false

# In tools/static_analysis.py — run_bandit() is called with mock=False automatically
# For Rust: pass the actual project directory to run_cargo_audit(project_path, mock=False)
```

---

## Security Constraints Built into the System

The system itself follows the principles it enforces:

| Concern | Mitigation |
|---------|------------|
| API key exposure | Required via env var only — `_require_env()` raises immediately if absent |
| Secrets in code | `.env` in `.gitignore`, `.env.example` has no real values |
| Output files with sensitive code | `output/` excluded from git by default |
| Dependency pinning | All packages in `requirements.txt` are pinned to exact versions |
| Subprocess injection | All subprocess calls use list form (no `shell=True`) |
| Tool timeout | All subprocess calls have explicit `timeout=` parameters |

---

## Test Coverage

Run tests (no LLM/API key required):
```bash
pip install pytest
python -m pytest tests/test_pipeline.py -v
```

The test suite covers:
- AST security checker (clean, eval, pickle, marshal, syntax errors)
- Bandit mock detection (shell=True, MD5, yaml.load)
- Cargo mock reports (audit, clippy, graceful failure)
- Tool dispatcher (language routing, error handling)
- Verdict parser state machine (approved, rejected, escalated)
- Code block extractor (fenced, multi-block, fallback)
- Report writer (JSON/Markdown file creation, valid JSON)
- Integration: vulnerable vs. secure code severity comparison

---

## Extending the System

### Add a new language (e.g. Go)

1. Add Go-specific checks in `tools/static_analysis.py`:
```python
def run_go_vet(go_code: str, mock: bool = False) -> ToolReport:
    # Wrap `go vet` and `gosec` here
    ...
```

2. Update the dispatcher in `run_all_tools()`:
```python
elif language.lower() == "go":
    reports.append(run_go_vet(code, mock=mock).to_llm_context())
```

3. Update `BUILDER_SYSTEM_PROMPT` to include Go-specific security rules.

### Add a fourth agent (e.g. a Compliance Mapper)

```python
# In agents/agent_definitions.py:
def create_compliance_agent(llm) -> Agent:
    return Agent(
        role="Compliance Mapper",
        goal="Map approved code to relevant compliance frameworks (SOC2, PCI-DSS, HIPAA)",
        ...
    )
```

Add a `compliance_node` to the LangGraph graph, wired after `approved_node`.

---

## Academic References

- OWASP Top 10: https://owasp.org/Top10/
- CWE/SANS Top 25: https://cwe.mitre.org/top25/
- LangGraph documentation: https://langchain-ai.github.io/langgraph/
- CrewAI documentation: https://docs.crewai.com/
- Rust security guidelines: https://anssi-fr.github.io/rust-guide/
- Bandit (Python security linter): https://bandit.readthedocs.io/
- cargo-audit: https://github.com/rustsec/rustsec

---

*Built as a Master's-level CS project demonstrating multi-agent AI systems, adversarial security review, and secure software development practices.*
