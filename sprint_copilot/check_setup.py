"""
check_setup.py — verify every credential works before building anything.

Run:  python -m sprint_copilot.check_setup   (from the project folder)

It only READS (GitHub /user, Jira /myself, one tiny Azure completion) except
the Slack check, which posts one clearly-labelled test message to your
channel. It never prints your secrets — only ✓/✗ and a short reason.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
import requests

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


# True only if a real value is filled in (not empty, not REPLACE_ME)
def _set(v: str | None) -> bool:
    return bool(v) and "REPLACE_ME" not in v and v.strip() != ""


# GET /user -> 200 means the GitHub token works
def check_github() -> tuple[bool, str]:
    tok = os.getenv("GITHUB_TOKEN", "")
    if not _set(tok):
        return False, "GITHUB_TOKEN not set"
    r = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    if r.status_code == 200:
        return True, f"authenticated as {r.json().get('login')}"
    return False, f"HTTP {r.status_code}"


# GET /myself -> 200 means the Jira login works
def check_jira() -> tuple[bool, str]:
    base = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_EMAIL", "")
    tok = os.getenv("JIRA_API_TOKEN", "")
    if not all(_set(x) for x in (base, email, tok)):
        return False, "JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN not all set"
    r = requests.get(
        f"{base.rstrip('/')}/rest/api/3/myself",
        auth=(email, tok),
        headers={"Accept": "application/json"},
        timeout=10,
    )
    if r.status_code == 200:
        return True, f"authenticated as {r.json().get('displayName')}"
    return False, f"HTTP {r.status_code} (check email + token + base URL)"


# Send a tiny test prompt to the AI
def check_azure_openai() -> tuple[bool, str]:
    for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"):
        if not _set(os.getenv(k, "")):
            return False, f"{k} not set"
    try:
        from sprint_copilot.llm import llm
        out = llm("You are a connectivity test.", "Reply with exactly: ok", max_tokens=5)
        return (bool(out), f"model replied: {out[:20]!r}")
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:110]}"


# Post one test message to the Slack channel
def check_slack() -> tuple[bool, str]:
    url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not _set(url):
        return False, "SLACK_WEBHOOK_URL not set"
    r = requests.post(
        url,
        json={"text": "✅ Sprint Copilot setup check — please ignore this test message."},
        timeout=10,
    )
    if r.status_code == 200:
        return True, "test message posted to the channel"
    return False, f"HTTP {r.status_code}: {r.text[:60]}"


def main() -> None:
    checks = [
        ("GitHub", check_github),
        ("Jira", check_jira),
        ("Azure OpenAI", check_azure_openai),
        ("Slack", check_slack),
    ]
    print("Sprint Copilot — Phase 0 setup check")
    print("=" * 50)
    all_ok = True
    for name, fn in checks:
        try:
            ok, msg = fn()
        except Exception as exc:
            ok, msg = False, f"{type(exc).__name__}: {str(exc)[:110]}"
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<14} {msg}")
    print("=" * 50)
    if all_ok:
        print("All green — Phase 0 is done. Ready to build.")
    else:
        print("Fill the FAIL items in .env, then run this again.")


if __name__ == "__main__":
    main()
