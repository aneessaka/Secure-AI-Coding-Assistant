"""Tests for github_bot URL validation."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from github_bot.url_validator import URLValidator


class TestURLValidator:
    def test_allows_public_https(self):
        assert URLValidator.is_safe_url("https://example.com/path")

    def test_blocks_localhost(self):
        assert not URLValidator.is_safe_url("http://localhost:8080")
        assert not URLValidator.is_safe_url("http://127.0.0.1")

    def test_blocks_private_ip(self):
        assert not URLValidator.is_safe_url("http://192.168.1.1")
        assert not URLValidator.is_safe_url("http://10.0.0.5")

    def test_blocks_metadata_endpoint(self):
        assert not URLValidator.is_safe_url("http://169.254.169.254/latest/meta-data")

    def test_sanitize_strips_fragment(self):
        assert URLValidator.sanitize_url("https://example.com/a#frag") == "https://example.com/a"
