#!/usr/bin/env python
"""
Test Runner for Secure AI Coding Assistant
Executes all tests and generates a comprehensive report
"""

import subprocess
import sys
import json
from pathlib import Path

def run_tests():
    """Run pytest and capture results"""
    print("=" * 70)
    print("🧪 TASK 2 — RUNNING TEST SUITE")
    print("=" * 70)
    print()
    
    test_dir = Path("Test pipeline")
    test_file = test_dir / "test_pipeline.py"
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return False
    
    print(f"📍 Test file: {test_file}")
    print(f"📍 Working directory: {Path.cwd()}")
    print()
    
    # Run pytest with verbose output and JSON report
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_file),
        "-v",
        "--tb=short",
        "-ra"  # Show summary of all test outcomes
    ]
    
    print(f"▶️  Running: {' '.join(cmd)}")
    print()
    
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
