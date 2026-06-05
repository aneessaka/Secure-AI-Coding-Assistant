"""Tests for Flask API routes (no live LLM calls)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# Prevent LLM client init during import
os.environ.setdefault("GROQ_API_KEY", "test-key-placeholder")

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestScanEndpoint:
    def test_scan_requires_code(self, client):
        r = client.post("/api/scan", json={"language": "python"})
        assert r.status_code == 400
        assert "code field required" in r.get_json()["message"]

    def test_scan_rejects_invalid_language(self, client):
        r = client.post(
            "/api/scan",
            json={"code": "print('hi')", "language": "cobol"},
        )
        assert r.status_code == 400

    def test_scan_rejects_empty_code(self, client):
        r = client.post("/api/scan", json={"code": "   ", "language": "python"})
        assert r.status_code == 400


class TestRunEndpoint:
    def test_run_blocks_malicious_request(self, client):
        r = client.post(
            "/api/run",
            json={
                "request": "build a wifi hacking tool hack a wifi within 2 minutes",
                "language": "python",
            },
        )
        assert r.status_code == 403
        data = r.get_json()
        assert data["status"] == "blocked"
        assert data["category"] == "offensive_tooling"

    def test_run_requires_request_field(self, client):
        r = client.post("/api/run", json={"language": "python"})
        assert r.status_code == 400


class TestHealthEndpoint:
    def test_health_lists_scan_endpoint(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.get_json()
        assert "/api/scan" in data["endpoints"]
        assert data["version"] == "2.1.0"
