"""GitHub PR security bot — scans pull request diffs and posts findings."""

from github_bot.bot import process_pull_request, verify_webhook_signature

__all__ = ["process_pull_request", "verify_webhook_signature"]
