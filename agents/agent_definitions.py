"""
agents/agent_definitions.py
----------------------------
Defines the three agents and their associated tasks using CrewAI.
Each agent is tightly bound to its system prompt and has explicit
constraints on what tools it may access.
"""

from crewai import Agent, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompts.system_prompts import (
    BUILDER_SYSTEM_PROMPT,
    HACKER_SYSTEM_PROMPT,
    AUDITOR_SYSTEM_PROMPT,
)
from tools.static_analysis import run_all_tools


# ---------------------------------------------------------------------------
# Custom Tool: Static Analysis Runner (for Auditor Agent)
# ---------------------------------------------------------------------------

class StaticAnalysisInput(BaseModel):
    """Input schema for the static analysis tool."""
    code: str = Field(description="The source code to analyze.")
    language: str = Field(
        description="Programming language of the code: 'python' or 'rust'.",
        default="python",
    )
    mock: bool = Field(
        description="Use mock tool output (True for dev/test, False for production).",
        default=True,
    )


class StaticAnalysisTool(BaseTool):
    """
    Runs real static analysis tools (Bandit for Python, Cargo Clippy/Audit for Rust)
    and returns structured findings for the Auditor agent to incorporate into its decision.

    This tool gives the Auditor ground truth beyond LLM reasoning alone.
    """
    name: str = "StaticAnalysisTool"
    description: str = (
        "Runs automated static analysis security tools on source code. "
        "For Python: runs AST analysis and Bandit. "
        "For Rust: runs Cargo Clippy and Cargo Audit. "
        "Returns structured findings including severity, CWE references, and locations. "
        "Always call this tool before issuing a final verdict."
    )
    args_schema: Type[BaseModel] = StaticAnalysisInput

    def _run(self, code: str, language: str = "python", mock: bool = True) -> str:
        """Execute the static analysis and return formatted results."""
        try:
            result = run_all_tools(code=code, language=language, mock=mock)
            return result
        except Exception as e:
            return (
                f"## Static Analysis Tool — ERROR\n"
                f"Tool execution failed: {str(e)}\n"
                f"The Auditor must note this failure and flag the report accordingly.\n"
                f"Do NOT approve code when automated analysis cannot be confirmed.\n"
            )


# ---------------------------------------------------------------------------
# Agent Factory Functions
# ---------------------------------------------------------------------------

def create_builder_agent(llm) -> Agent:
    """
    The Builder: produces secure, production-ready code.
    Has NO tools — code generation is its sole output.
    Bound strictly to BUILDER_SYSTEM_PROMPT.
    """
    return Agent(
        role="Senior Software Engineer (The Builder)",
        goal=(
            "Generate production-ready, secure-by-default code that passes both "
            "red team security review and automated static analysis without modifications."
        ),
        backstory=BUILDER_SYSTEM_PROMPT,
        llm=llm,
        tools=[],  # Builder has no tools — pure code generation
        verbose=True,
        allow_delegation=False,
        max_iter=1,  # One shot per loop iteration
    )


def create_hacker_agent(llm) -> Agent:
    """
    The Red Team Hacker: offensive security reviewer.
    Has NO tools — attack analysis is pure LLM reasoning.
    Bound strictly to HACKER_SYSTEM_PROMPT.
    """
    return Agent(
        role="Senior Penetration Tester — ADVERSARY-1 (The Red Team Hacker)",
        goal=(
            "Exhaustively identify every security vulnerability in the provided code. "
            "Produce a structured Red Team Report that covers all OWASP Top 10 categories "
            "and SANS Top 25 CWEs. Leave nothing unchecked."
        ),
        backstory=HACKER_SYSTEM_PROMPT,
        llm=llm,
        tools=[],  # Hacker uses only LLM reasoning — no external tool access
        verbose=True,
        allow_delegation=False,
        max_iter=1,
    )


def create_auditor_agent(llm) -> Agent:
    """
    The Security Auditor: gatekeeper with programmatic tool access.
    This agent has the StaticAnalysisTool — giving it ground truth
    beyond LLM reasoning. It synthesizes tool output + Red Team report
    to produce a final APPROVED or REJECTED verdict.
    """
    static_analysis_tool = StaticAnalysisTool()

    return Agent(
        role="Security Compliance Officer (The Auditor)",
        goal=(
            "Synthesize the Red Team Hacker's report with automated static analysis tool output "
            "to produce a definitive APPROVED or REJECTED verdict with a precise Remediation Brief. "
            "You MUST call the StaticAnalysisTool before issuing any verdict."
        ),
        backstory=AUDITOR_SYSTEM_PROMPT,
        llm=llm,
        tools=[static_analysis_tool],
        verbose=True,
        allow_delegation=False,
        max_iter=3,  # Allow tool call retries
    )


# ---------------------------------------------------------------------------
# Task Factory Functions
# ---------------------------------------------------------------------------

def create_build_task(agent: Agent, user_request: str, iteration: int,
                      remediation_brief: str = "") -> Task:
    """
    Create the Builder's coding task.

    Args:
        agent: The Builder agent.
        user_request: The original user's code request.
        iteration: Current loop iteration (1-3).
        remediation_brief: If iteration > 1, the Auditor's fix instructions.
    """
    if iteration == 1:
        description = f"""
Generate secure, production-ready code for the following request:

## USER REQUEST:
{user_request}

## INSTRUCTIONS:
- Follow your system prompt defaults (prefer Rust, use secure libraries).
- Structure your output with: DESIGN RATIONALE → CODE BLOCK → DEPENDENCIES → KNOWN LIMITATIONS.
- This is iteration {iteration} of 3. Write your best, most secure code on the first attempt.
- Do NOT use placeholder security. All validation, error handling, and auth must be real.
"""
    else:
        description = f"""
Revise your previously generated code based on the Security Auditor's Remediation Brief.

## ORIGINAL USER REQUEST:
{user_request}

## SECURITY AUDITOR'S REMEDIATION BRIEF (Iteration {iteration - 1}):
{remediation_brief}

## INSTRUCTIONS:
- You MUST address EVERY mandatory fix in the Remediation Brief.
- For each fix: acknowledge the vulnerability, explain your remediation, apply it.
- Regenerate the ENTIRE code file — no partial patches.
- This is iteration {iteration} of 3.
"""

    return Task(
        description=description,
        expected_output=(
            "A complete, structured code response containing:\n"
            "1. DESIGN RATIONALE section\n"
            "2. Full, complete CODE BLOCK with inline security comments\n"
            "3. DEPENDENCIES section with pinned versions\n"
            "4. KNOWN LIMITATIONS section\n"
            "The code must be syntactically correct and immediately runnable."
        ),
        agent=agent,
    )


def create_attack_task(agent: Agent, builder_output: str, iteration: int) -> Task:
    """
    Create the Red Team Hacker's attack review task.

    Args:
        agent: The Hacker agent.
        builder_output: The Builder's generated code (full response).
        iteration: Current loop iteration.
    """
    return Task(
        description=f"""
Perform an exhaustive security review of the following code. This is iteration {iteration} of 3.

## CODE UNDER REVIEW:
{builder_output}

## INSTRUCTIONS:
- Execute your full attack methodology: check ALL Tier 1, Tier 2, and Tier 3 categories.
- Produce a structured Red Team Report in EXACTLY the format specified in your system prompt.
- Be especially thorough on iteration {iteration} — previous issues may have been patched
  but root causes sometimes remain. Look for regression and incomplete fixes.
- Verdict options: CRITICAL_FAIL | HIGH_FAIL | MEDIUM_WARN | PASS
- PASS only if you have EXHAUSTIVELY checked every tier and found NOTHING exploitable.
""",
        expected_output=(
            "A complete Red Team Report in the exact format specified:\n"
            "- Header with Verdict (CRITICAL_FAIL | HIGH_FAIL | MEDIUM_WARN | PASS)\n"
            "- Numbered findings with Severity, CWE-ID, Location, Description, Attack Vector, PoC, Remediation Hint\n"
            "- Summary section with counts by severity and overall risk assessment\n"
            "The report must be clinical, precise, and thorough."
        ),
        agent=agent,
    )


def create_audit_task(agent: Agent, builder_output: str, hacker_report: str,
                      iteration: int, language: str = "python") -> Task:
    """
    Create the Security Auditor's verdict task.

    Args:
        agent: The Auditor agent.
        builder_output: Builder's generated code.
        hacker_report: Red Team Hacker's full report.
        iteration: Current loop iteration.
        language: Programming language for tool selection.
    """
    # Extract just the code block from builder output for tool analysis
    code_for_analysis = _extract_code_block(builder_output)

    return Task(
        description=f"""
Issue your security verdict for iteration {iteration} of 3.

## BUILDER'S CODE:
{builder_output}

## RED TEAM HACKER'S REPORT:
{hacker_report}

## YOUR REQUIRED ACTIONS:
1. CALL the StaticAnalysisTool with the following parameters:
   - code: [extract the code block from the Builder's output]
   - language: "{language}"
   - mock: true
   
   Here is the extracted code for the tool call:
   ```
   {code_for_analysis}
   ```

2. After receiving tool results, synthesize:
   - The Red Team findings
   - The static analysis tool findings
   
3. Apply your decision framework:
   - AUTOMATIC REJECTION triggers? → REJECT immediately
   - RED TEAM verdict? → Weight accordingly
   - Tool findings → Cross-reference with Red Team

4. Output either:
   - REJECTED: Full Remediation Brief (if iteration < 3)
   - REJECTED + ESCALATION: If iteration 3 still has CRITICAL issues
   - APPROVED: Approval Certificate

## CRITICAL: 
You MUST call StaticAnalysisTool before issuing your verdict.
You MUST use the exact output format from your system prompt.
""",
        expected_output=(
            "One of two structured outputs:\n"
            "OPTION A — REJECTED: 'SECURITY AUDITOR — REMEDIATION BRIEF' with:\n"
            "  - Status: REJECTED\n"
            "  - Numbered mandatory fixes with root cause, required fix, acceptance criteria\n"
            "  - Recommendations section\n"
            "  - Static Analysis Tool Output section\n"
            "  - Iteration count and next action\n"
            "OPTION B — APPROVED: 'SECURITY AUDITOR — APPROVAL CERTIFICATE' with:\n"
            "  - Status: APPROVED\n"
            "  - Red Team and Static Analysis confirmation\n"
            "  - Summary and caveats\n"
        ),
        agent=agent,
    )


def _extract_code_block(text: str) -> str:
    """
    Best-effort extraction of a code block from agent output.
    Looks for ``` fences and returns the largest block.
    Falls back to the full text if no fences found.
    """
    import re
    # Match fenced code blocks (with or without language specifier)
    pattern = r"```(?:\w+)?\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)

    if matches:
        # Return the longest code block (usually the main implementation)
        return max(matches, key=len).strip()

    # Fallback: return the full text (Auditor will handle it)
    return text
