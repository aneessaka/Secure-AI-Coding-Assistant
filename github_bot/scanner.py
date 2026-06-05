"""Web vulnerability scanner (simulated for now; ZAP integration later)."""

import asyncio
import os

from github_bot.url_validator import URLValidator


class WebScanner:
    """Placeholder scanner for web vulnerabilities."""

    def __init__(self):
        self._sim_delay = float(os.getenv("WEB_SCAN_SIM_DELAY", "1"))

    async def scan_url(self, target_url: str, depth: str = "standard") -> dict:
        """
        Simulate a scan. Returns a dict with findings or an error key.
        Real implementation will call ZAP or similar.
        """
        safe_url = URLValidator.sanitize_url(target_url)
        if not URLValidator.is_safe_url(safe_url):
            return {
                "error": "invalid_url",
                "details": "URL is not allowed (internal, localhost, or private IP).",
            }

        if self._sim_delay > 0:
            await asyncio.sleep(self._sim_delay)

        return {
            "total_findings": 1,
            "scan_time": "2025-01-01 12:00:00",
            "findings": [
                {
                    "name": "Test Finding",
                    "severity": "MEDIUM",
                    "url": safe_url,
                    "description": "Simulated finding to verify the /scan PR command flow.",
                    "solution": "Replace with real scanner integration.",
                    "cwe_id": "N/A",
                }
            ],
        }

    def scan_url_sync(self, target_url: str, depth: str = "standard") -> dict:
        """Thread-safe entry point for Flask/gunicorn background workers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.scan_url(target_url, depth))
        finally:
            loop.close()
