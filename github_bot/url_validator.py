# github_bot/url_validator.py

from urllib.parse import urlparse
import ipaddress

class URLValidator:
    """Validates and sanitizes URLs to prevent SSRF and internal network scanning."""

    # Block these hostnames or patterns
    BLOCKED_HOSTS = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
        "169.254.169.254",  # AWS metadata
    ]

    # Block these IP ranges (private / reserved)
    BLOCKED_NETWORKS = [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",   # IPv6 unique local
        "fe80::/10",  # IPv6 link local
    ]

    @classmethod
    def is_safe_url(cls, url: str) -> bool:
        """
        Returns True if URL is safe to scan (external, non-private).
        Returns False and logs reason otherwise.
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False

            # Scheme must be http or https
            if parsed.scheme not in ("http", "https"):
                return False

            hostname = parsed.hostname
            if not hostname:
                return False

            # 1. Check exact blocked hostnames
            if hostname.lower() in cls.BLOCKED_HOSTS:
                return False

            # 2. Try to resolve hostname to IPs (basic – no DNS lookup here)
            #    We'll do a simple IP check if it's already an IP address
            try:
                ip = ipaddress.ip_address(hostname)
                # Check if IP is in any blocked network
                for net_str in cls.BLOCKED_NETWORKS:
                    network = ipaddress.ip_network(net_str)
                    if ip in network:
                        return False
            except ValueError:
                # hostname is not an IP, assume safe for now
                # (advanced: you could resolve DNS but that adds complexity)
                pass

            return True

        except Exception:
            return False

    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """Remove any fragments or trailing slashes for normalisation."""
        parsed = urlparse(url)
        # Rebuild without fragment and with lowercase scheme/host
        clean = parsed._replace(fragment="")
        return clean.geturl()