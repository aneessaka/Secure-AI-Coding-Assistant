"""
config/settings.py
------------------
Centralized configuration management.
All secrets must come from environment variables — never hardcoded.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    """
    Application settings loaded from environment variables.
    
    Required environment variables:
        ANTHROPIC_API_KEY: Your Anthropic API key.
    
    Optional environment variables (with defaults):
        MODEL_NAME: Claude model to use (default: claude-sonnet-4-20250514)
        TEMPERATURE: LLM temperature 0.0-1.0 (default: 0.1 — low for consistency)
        MAX_TOKENS: Max tokens per response (default: 4096)
        VERBOSE: Enable verbose CrewAI output (default: true)
        USE_MOCK_TOOLS: Use mock static analysis tools (default: true)
        OUTPUT_DIR: Directory for saving reports (default: ./output)
        MAX_ITERATIONS: Maximum revision loops (default: 3, max: 5)
    """

    # --- Required ---
    anthropic_api_key: str = field(default_factory=lambda: _require_env("ANTHROPIC_API_KEY"))

    # --- LLM Settings ---
    model_name: str = field(
        default_factory=lambda: os.getenv("MODEL_NAME", "claude-sonnet-4-20250514")
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOKENS", "4096"))
    )

    # --- Pipeline Settings ---
    max_iterations: int = field(
        default_factory=lambda: min(int(os.getenv("MAX_ITERATIONS", "3")), 5)
    )
    use_mock_tools: bool = field(
        default_factory=lambda: os.getenv("USE_MOCK_TOOLS", "true").lower() == "true"
    )

    # --- Output Settings ---
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./output"))
    )

    # --- Debug Settings ---
    verbose: bool = field(
        default_factory=lambda: os.getenv("VERBOSE", "true").lower() == "true"
    )


def _require_env(key: str) -> str:
    """Load a required environment variable or raise a clear error."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"\n\n❌ Required environment variable '{key}' is not set.\n"
            f"   Set it with: export {key}='your-value-here'\n"
            f"   Or create a .env file (see .env.example)\n"
        )
    return value
