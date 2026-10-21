"""
slack.py — Phase 6: post the standup to Slack.

Uses the Incoming Webhook in SLACK_WEBHOOK_URL — a single POST, no OAuth.
The standup already uses Slack-friendly formatting (*bold*, • bullets), so
it renders cleanly in the channel.
"""

import os
from datetime import date

import requests


# Send text to Slack via the webhook (a secret URL for one channel)
def post_message(text: str, webhook: str | None = None) -> int:
    url = webhook or os.environ["SLACK_WEBHOOK_URL"]
    # POST = send data (GET = read data)
    r = requests.post(url, json={"text": text}, timeout=10)
    r.raise_for_status()
    return r.status_code


# Write the standup and post it with a date header
def post_standup(work_items: dict | None = None) -> str:
    """Generate the standup and post it. Returns the standup text."""
    from sprint_copilot.standup import generate_standup
    standup, _ = generate_standup(work_items)
    header = f":sunrise: *Sprint Copilot — Daily Standup ({date.today().isoformat()})*\n\n"
    post_message(header + standup)
    return standup


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from dotenv import load_dotenv
    from sprint_copilot import match as matcher

    load_dotenv(Path(__file__).parent.parent / ".env")

    work_items = matcher._SAMPLE if "--sample" in sys.argv else None

    # --dry: build the standup but DON'T post it
    if "--dry" in sys.argv:
        # Build the standup but DON'T post — just print it.
        from sprint_copilot.standup import generate_standup
        text, _ = generate_standup(work_items)
        print("--- would post to Slack ---\n")
        print(text)
    else:
        text = post_standup(work_items)
        print("Posted to Slack:\n")
        print(text)
