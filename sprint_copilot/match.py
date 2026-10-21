"""
match.py — Phase 4: connect GitHub activity to Jira tickets.

Links each commit / PR / branch to a ticket by the ticket key it mentions
(e.g. "SCRUM-1" in a commit message, PR title, or branch name like
"feature/SCRUM-1-login").

build_work_items() combines the GitHub half (github.py) and the Jira half
(jira.py) into one dict; match() annotates each ticket with the activity
that references it, and collects activity that references no known ticket.

This is the join the standup (Phase 5) and stuck-detection (Phase 8) read.
"""

import json
import re
from pathlib import Path

from sprint_copilot import github, jira

# A Jira-style key: uppercase project code + number, e.g. SCRUM-1, ABC-123.
# Regex for a ticket key: capital letters, a dash, a number -> e.g. SCRUM-1
_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

# Manual, human-made links (commit hash -> ticket key), for when the
# automatic text-matching misses or gets it wrong. Persisted next to the
# code so they survive restarts.
_LINKS_FILE = Path(__file__).parent / "manual_links.json"


# Read links a human made by hand (commit hash -> ticket key)
def load_manual_links() -> dict:
    try:
        return json.loads(_LINKS_FILE.read_text())
    except Exception:
        return {}


# Save one manual link so it survives a restart
def save_manual_link(commit_hash: str, ticket_key: str) -> None:
    links = load_manual_links()
    links[commit_hash] = ticket_key
    _LINKS_FILE.write_text(json.dumps(links, indent=2))


# Find all ticket keys in any number of texts; a set removes duplicates
def extract_keys(*texts: str) -> set[str]:
    keys: set[str] = set()
    for t in texts:
        if t:
            keys.update(_KEY_RE.findall(t))
    return keys


# Read GitHub + Jira and put everything into one dictionary
def build_work_items() -> dict:
    """Pull both halves (real data) into the shared shape."""
    gh = github.build_github_data()
    return {
        "repo": gh["repo"],
        "tickets": jira.fetch_tickets(),
        "commits": gh["commits"],
        "prs": gh["prs"],
        "branches": gh["branches"],
    }


# Connect commits / PRs / branches to their tickets ('sort letters into mailboxes')
def match(work_items: dict) -> dict:
    """Annotate tickets with their linked commits/PRs/branches; collect the
    activity that matched no known ticket."""
    # One empty 'mailbox' per ticket
    by_key: dict[str, dict] = {
        t["key"]: {"ticket": t, "commits": [], "prs": [], "branches": []}
        for t in work_items.get("tickets", [])
    }

    linked_commits: set[str] = set()
    linked_prs: set[int] = set()

    # Commits: look for ticket keys in the commit message
    for c in work_items.get("commits", []):
        for k in extract_keys(c.get("message", "")):
            # Only keys of REAL tickets count (ignores text like UTF-8)
            if k in by_key:
                by_key[k]["commits"].append(c)
                linked_commits.add(c["hash"])

    # PRs: look in the title and the branch name
    for p in work_items.get("prs", []):
        for k in extract_keys(p.get("title", ""), p.get("branch", "")):
            if k in by_key:
                by_key[k]["prs"].append(p)
                linked_prs.add(p["number"])

    # Branches: look in the branch name
    for b in work_items.get("branches", []):
        for k in extract_keys(b):
            if k in by_key:
                by_key[k]["branches"].append(b)

    # Apply human-made manual links (commit hash -> ticket key).
    # Human override: apply manual links for commits without a key
    manual = load_manual_links()
    for c in work_items.get("commits", []):
        tk = manual.get(c["hash"])
        if tk in by_key and c["hash"] not in linked_commits:
            by_key[tk]["commits"].append(c)
            linked_commits.add(c["hash"])

    return {
        "repo": work_items.get("repo", ""),
        "matched": by_key,
        # Activity with no ticket goes to an 'unmatched' list
        "unmatched_commits": [c for c in work_items.get("commits", []) if c["hash"] not in linked_commits],
        "unmatched_prs": [p for p in work_items.get("prs", []) if p["number"] not in linked_prs],
    }


def print_report(result: dict) -> None:
    print(f"Repo: {result['repo']}\n")
    any_link = False
    for key, m in result["matched"].items():
        t = m["ticket"]
        n = len(m["commits"]) + len(m["prs"]) + len(m["branches"])
        if n == 0:
            continue
        any_link = True
        print(f"{key} [{t['status']}] {t['title']}  → {t['assignee']}")
        for p in m["prs"]:
            print(f"    PR  #{p['number']} [{p['state']}] {p['title']}")
        for c in m["commits"]:
            print(f"    commit {c['short_hash']} {c['message'].splitlines()[0][:60]}")
        for b in m["branches"]:
            print(f"    branch {b}")
    if not any_link:
        print("(No commits/PRs/branches reference a ticket key yet.)")
        print("Seed one: create a branch like 'feature/SCRUM-1-login' and a PR whose")
        print("title/branch contains SCRUM-1 — then matching will link it.\n")
    print(f"Unmatched: {len(result['unmatched_commits'])} commit(s), "
          f"{len(result['unmatched_prs'])} PR(s) with no ticket key.")


# A tiny fake dataset so the matching logic can be demonstrated even before
# any real branch uses a ticket key.
# Demo data: lets you test everything without real GitHub/Jira accounts
_SAMPLE = {
    "repo": "demo/repo",
    "tickets": [
        {"key": "SCRUM-1", "title": "Role-based login", "status": "In Progress", "assignee": "Alex"},
        {"key": "SCRUM-2", "title": "HR permissions", "status": "To Do", "assignee": "Shravani"},
        {"key": "SCRUM-3", "title": "Audit log", "status": "In Progress", "assignee": "Alex"},
    ],
    "commits": [
        {"hash": "aaa1", "short_hash": "aaa1", "message": "SCRUM-1 add login form", "author": "Alex"},
        {"hash": "bbb2", "short_hash": "bbb2", "message": "SCRUM-3 write audit entries", "author": "Alex"},
        {"hash": "ccc3", "short_hash": "ccc3", "message": "tidy up readme", "author": "Shravani"},
    ],
    "prs": [
        {"number": 4, "title": "SCRUM-1 login", "state": "merged", "branch": "feature/SCRUM-1-login", "merged": True},
        {"number": 5, "title": "chore: deps", "state": "open", "branch": "chore/deps", "merged": False},
    ],
    "branches": ["main", "feature/SCRUM-1-login", "feature/SCRUM-2-hr"],
}


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")

    if "--sample" in sys.argv:
        print("=== SAMPLE DATA (proves the matching logic) ===\n")
        print_report(match(_SAMPLE))
    else:
        print("=== REAL DATA (GitHub + Jira) ===\n")
        print_report(match(build_work_items()))
