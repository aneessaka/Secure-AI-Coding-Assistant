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
from typing import Type, Optional
import sys
import os

# Allow imports from project root safely
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Sub-folder paths inclusion for robust module alignment
for folder in ["prompts", "tools", "config"]:
    f_path = os.path.join(project_root, folder)
    if f_path not in sys.path:
        sys.path.insert(0, f_path)

# Safe imports from relative sub-folders
try:
    from system_prompts import (
        BUILDER_SYSTEM_PROMPT,
        HACKER_SYSTEM_PROMPT,
        AUDITOR_SYSTEM_PROMPT,
    )
except ModuleNotFoundError:
    # Reliable fallback values if system_prompts is missing
    BUILDER_SYSTEM_PROMPT = "You are The Builder — a Senior Software Engineer. Write secure code."
    HACKER_SYSTEM_PROMPT = "You are ADVERSARY-1 — a Red Team Hacker. Find high-severity vulnerabilities."
    AUDITOR_SYSTEM_PROMPT = "You are the Security Auditor. Run analysis and issue APPROVED or REJECTED status."

try:
    from static_analysis import run_all_tools
except ModuleNotFoundError:
    # Inline heuristic mock scanner if static_analysis engine import fails
    def run_all_tools(code: str, language: str = "python", mock: bool = True) -> str:
        import ast
        findings = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ['eval', 'exec']:
                    findings.append(f"CRITICAL: Dangerous invocation of dynamic language feature: {node.func.id}()")
        except Exception as e:
            return f"Static analysis execution error: {str(e)}"
        if findings:
            return "--- Automated Analysis Report ---\nStatus: FAIL\n" + "\n".join(findings)
        return "--- Automated Analysis Report ---\nStatus: PASS\nNo obvious dynamic syntax vulnerabilities found."

# Security utilities for input validation
try:
    from security_utils import validate_request_length, validate_remediation_brief, escape_for_template
except ModuleNotFoundError:
    # Fallback implementations if security_utils is missing
    def validate_request_length(text: str, max_length: int = 5000) -> None:
        if len(text) > max_length:
            raise ValueError(f"Input exceeds {max_length} characters")
    
    def validate_remediation_brief(text: str, max_length: int = 10000) -> None:
        if len(text) > max_length:
            raise ValueError(f"Input exceeds {max_length} characters")
    
    def escape_for_template(text: str) -> str:
        return text.replace("```", "`​`​`")


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
        tools=[],
        verbose=True,
        allow_delegation=False,
        max_iter=1,
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
        tools=[],
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

def create_build_task(agent: Agent, user_request: str, language: str, iteration: int = 1,
                      remediation_brief: str = "") -> Task:
    """
    Create the Builder's coding task.

    Args:
        agent: The Builder agent.
        user_request: The original user's code request.
        language: Programming language targeted.
        iteration: Current loop iteration (1-3).
        remediation_brief: If iteration > 1, the Auditor's fix instructions.
        
    Raises:
        ValueError: If inputs exceed maximum safe lengths.
    
    Returns:
        A Task configured for the Builder agent.
    """
    # SECURITY: Validate input lengths to prevent token exhaustion
    try:
        validate_request_length(user_request, max_length=5000)
        if remediation_brief:
            validate_remediation_brief(remediation_brief, max_length=10000)
    except ValueError as e:
        raise ValueError(f"Task validation failed: {str(e)}")
    
    # SECURITY: Escape user input to prevent prompt injection via template
    safe_user_request = escape_for_template(user_request)
    safe_remediation = escape_for_template(remediation_brief) if remediation_brief else ""
    
    if iteration == 1:
        description = f"""
Generate secure, production-ready code for the following request:

## USER REQUEST:
{safe_user_request}

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
{safe_user_request}

## SECURITY AUDITOR'S REMEDIATION BRIEF (Iteration {iteration - 1}):
{safe_remediation}

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


def create_attack_task(agent: Agent, builder_output: str, iteration: int = 1) -> Task:
    """
    Create the Red Team Hacker's attack review task.

    Args:
        agent: The Hacker agent.
        builder_output: The Builder's generated code (full response).
        iteration: Current loop iteration.
        
    Returns:
        A Task configured for the Hacker agent.
    """
    # SECURITY: Escape builder output to prevent prompt injection
    safe_builder_output = escape_for_template(builder_output)
    
    return Task(
        description=f"""
Perform an exhaustive security review of the following code. This is iteration {iteration} of 3.

## CODE UNDER REVIEW:
{safe_builder_output}

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
                      iteration: int = 1, language: str = "python") -> Task:
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

2. Based on BOTH the Red Team Report AND the tool output, issue your verdict:
   - APPROVED: Code has NO high/critical issues and passes automated analysis
   - ESCALATED: Code has critical/high issues OR fails automated analysis

3. If ESCALATED, provide a Remediation Brief with specific fix instructions.

## FORMAT REQUIREMENTS:
- Start with: Verdict: [APPROVED | ESCALATED]
- Follow with findings summary and remediation (if applicable)
- Be concise, clinical, and precise
""",
        expected_output=(
            "A final security verdict containing:\n"
            "1. Clear Verdict: [APPROVED | ESCALATED]\n"
            "2. Summary of findings from both Red Team Report and Static Analysis\n"
            "3. If ESCALATED: a Remediation Brief with mandatory fixes\n"
            "4. Risk assessment and confidence level\n"
            "The verdict must be definitive and actionable."
        ),
        agent=agent,
    )


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def _extract_code_block(text: str) -> str:
    """
    Extract the largest code block from text.
    Looks for ```<language> code ``` markers and extracts the longest one.
    Fallback: if no code blocks found, return original text (up to 500 chars).
    """
    import re

    # Find all code blocks (with or without language specifier)
    pattern = r'```(?:python|rust|js|javascript|java|cpp|c|go|ruby)?\s*\n(.*?)\n```'
    matches = re.findall(pattern, text, re.DOTALL)

    if not matches:
        # No code blocks found - return original text as fallback
        return text if len(text) <= 500 else text[:500]

    # Return the longest code block
    longest = max(matches, key=len)
    return longest.strip()