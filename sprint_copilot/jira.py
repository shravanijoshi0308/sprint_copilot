"""
jira.py — Phase 3: read the sprint's tickets (and, later, act on them).

Pulls issues for a project into the shared work_items shape:
    "tickets": [{key, title, status, assignee, updated, url}]

Config from .env: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT.
Auth is HTTP basic (email + API token).

Jira Cloud is migrating its search API, so fetch_tickets tries the newer
/rest/api/3/search/jql endpoint and falls back to the classic
/rest/api/3/search if that isn't available.
"""

import os
import requests

# Only ask Jira for the fields we actually use
_FIELDS = ["summary", "status", "assignee", "updated", "created"]


# Jira login details from .env (base URL, email, API token)
def _cfg() -> tuple[str, str, str]:
    return (
        os.environ["JIRA_BASE_URL"].rstrip("/"),
        os.environ["JIRA_EMAIL"],
        os.environ["JIRA_API_TOKEN"],
    )


# Which Jira project to read (default: SCRUM)
def _project() -> str:
    return os.environ.get("JIRA_PROJECT", "SCRUM")


# Used when JIRA_PROJECT=ALL: list every project the account can see
def all_project_keys() -> list[str]:
    """Every project the account can see — so a newly-added project shows up
    with no config change (set JIRA_PROJECT=ALL to use this)."""
    base, email, token = _cfg()
    r = requests.get(
        f"{base}/rest/api/3/project/search",
        auth=(email, token), headers={"Accept": "application/json"},
        params={"maxResults": 50}, timeout=15,
    )
    r.raise_for_status()
    return [p["key"] for p in r.json().get("values", [])]


# Turn Jira's big nested answer into a small, simple ticket dictionary
def _normalise(issue: dict, base: str) -> dict:
    f = issue.get("fields", {}) or {}
    # `or {}` -> if there is no assignee, use an empty dict so .get() below can't crash
    assignee = f.get("assignee") or {}
    status = f.get("status") or {}
    return {
        "key": issue.get("key", ""),
        "title": f.get("summary", ""),
        "status": status.get("name", ""),
        "assignee": assignee.get("displayName", "Unassigned"),
        "updated": f.get("updated", ""),
        "url": f"{base}/browse/{issue.get('key', '')}",
    }


# Read the sprint's tickets using a JQL search
def fetch_tickets(project: str | None = None, jql: str | None = None, max_results: int = 50) -> list[dict]:
    base, email, token = _cfg()
    project = project or _project()
    if jql is None:
        # JIRA_PROJECT=ALL (or *) → every project the account can see, so a
        # newly-added project appears automatically. Otherwise it's a
        # comma-separated list of specific project keys.
        if project.strip().upper() in ("ALL", "*", ""):
            keys = all_project_keys()
        else:
            keys = [k.strip() for k in project.split(",") if k.strip()]
        scope = f"project = {keys[0]}" if len(keys) == 1 else f"project in ({', '.join(keys)})"
        # JQL = Jira's search language: these projects, newest updates first
        jql = f"{scope} ORDER BY updated DESC"
    auth = (email, token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    # Newer enhanced-search endpoint first.
    # Try the NEW Jira search API first
    r = requests.post(
        f"{base}/rest/api/3/search/jql",
        auth=auth, headers=headers,
        json={"jql": jql, "fields": _FIELDS, "maxResults": max_results},
        timeout=15,
    )
    # 404/410 = new API not available here -> fall back to the OLD search API
    if r.status_code in (404, 410):
        r = requests.get(
            f"{base}/rest/api/3/search",
            auth=auth, headers=headers,
            params={"jql": jql, "fields": ",".join(_FIELDS), "maxResults": max_results},
            timeout=15,
        )
    r.raise_for_status()

    return [_normalise(it, base) for it in r.json().get("issues", [])]


# ── Write-back: move a ticket ─────────────────────────────────────────────────

# Ask Jira which status moves are allowed for this ticket right now
def get_transitions(key: str) -> list[dict]:
    """The workflow transitions currently available for an issue."""
    base, email, token = _cfg()
    r = requests.get(
        f"{base}/rest/api/3/issue/{key}/transitions",
        auth=(email, token), headers={"Accept": "application/json"}, timeout=15,
    )
    r.raise_for_status()
    return r.json().get("transitions", [])


# Move a ticket (e.g. to Done). SAFE: dry_run=True only reports, changes nothing
def move_issue(key: str, target: str = "Done", dry_run: bool = True) -> tuple[bool, str]:
    """Move an issue to a status matching `target` (e.g. "Done").

    dry_run=True (default) only reports what it would do — nothing changes on
    the board. Pass dry_run=False to actually perform the transition.
    """
    transitions = get_transitions(key)
    chosen = None
    for tr in transitions:
        to_name = (tr.get("to") or {}).get("name", "")
        # Find a transition that leads to the target status (case-insensitive)
        if target.lower() in to_name.lower() or target.lower() in tr.get("name", "").lower():
            chosen = tr
            break

    # No allowed path to the target -> explain, don't guess
    if not chosen:
        available = ", ".join((t.get("to") or {}).get("name", "?") for t in transitions)
        return False, f"{key}: no transition to '{target}' (available: {available or 'none'})"

    to_name = chosen["to"]["name"]
    # Dry-run: stop here and only say what WOULD happen
    if dry_run:
        return True, f"{key}: WOULD move → {to_name} (transition '{chosen['name']}')"

    base, email, token = _cfg()
    r = requests.post(
        f"{base}/rest/api/3/issue/{key}/transitions",
        auth=(email, token),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"transition": {"id": chosen["id"]}},
        timeout=15,
    )
    r.raise_for_status()
    return True, f"{key}: moved → {to_name}"


# Write a comment on a ticket (also dry-run by default)
def add_comment(key: str, text: str, dry_run: bool = True) -> tuple[bool, str]:
    """Post a comment on an issue. Jira Cloud v3 needs Atlassian Document
    Format (ADF), so we wrap the plain text in a minimal doc."""
    if dry_run:
        return True, f"{key}: WOULD comment \"{text[:60]}...\""

    base, email, token = _cfg()
    # One ADF paragraph per line so multi-line comments render correctly.
    # Jira Cloud needs ADF format: one paragraph block per line of text
    paragraphs = [
        {"type": "paragraph", "content": [{"type": "text", "text": line or " "}]}
        for line in text.split("\n")
    ]
    body = {"body": {"type": "doc", "version": 1, "content": paragraphs}}
    r = requests.post(
        f"{base}/rest/api/3/issue/{key}/comment",
        auth=(email, token),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json=body, timeout=15,
    )
    r.raise_for_status()
    return True, f"{key}: comment posted"


if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
    tickets = fetch_tickets()
    print(f"Project {_project()} — {len(tickets)} ticket(s):\n")
    for t in tickets:
        print(f"  {t['key']:<10} [{t['status']:<12}] {t['title'][:50]:<50} — {t['assignee']}")
    if not tickets:
        print("  (none — check JIRA_PROJECT and that the sprint has tickets)")
