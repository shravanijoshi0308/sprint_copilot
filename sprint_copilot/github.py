"""
github.py — Phase 2: read what's happening in GitHub.

Pulls recent commits, pull requests, and branches for a repo into the shared
`work_items` shape that the rest of Sprint Copilot consumes. Read-only.

Repo comes from GITHUB_REPO in .env (e.g. "shravanijoshi0308/sprint-copilot"); auth from
GITHUB_TOKEN.

Output shape (the half github.py fills):
    {
      "repo": "owner/repo",
      "commits":  [{hash, short_hash, message, author, date, url}],
      "prs":      [{number, title, state, branch, author, merged,
                    created_at, updated_at, url}],
      "branches": ["main", "feature/SCRUM-1-login", ...]
    }
`state` is normalised to "open" / "closed" / "merged".
"""

import os
from datetime import datetime, timedelta, timezone

import requests

# Base address of the GitHub REST API
API = "https://api.github.com"


# The 'ID card' sent with every request: GitHub token from .env
def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }


# Use the repo passed in, or GITHUB_REPO from .env if none was given
def _repo(repo: str | None) -> str:
    return repo or os.environ.get("GITHUB_REPO", "")


# Read commits from ALL branches (work happens on feature branches)
def fetch_commits(repo: str | None = None, since_days: int = 14, per_branch: int = 50) -> list[dict]:
    """Commits across ALL branches, not just the default.

    Without a `sha` param the GitHub API only returns commits on the default
    branch (main) — which misses everything on feature branches, i.e. where
    the actual work happens. So we walk every branch and dedupe by SHA. Each
    commit is tagged with a branch it was found on, which also helps matching
    (branch names carry the ticket key).
    """
    repo = _repo(repo)
    # Only look at the last `since_days` days (about one sprint)
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    # Remember commit IDs (SHA) we already added -> no duplicates
    seen: set[str] = set()
    out: list[dict] = []

    for branch in fetch_branches(repo):
        r = requests.get(
            f"{API}/repos/{repo}/commits",
            headers=_headers(),
            params={"sha": branch, "since": since, "per_page": per_branch},
            timeout=15,
        )
        # If one branch fails, skip it and keep going (don't crash)
        if r.status_code != 200:
            continue
        for c in r.json():
            sha = c["sha"]
            # Same commit can be on several branches after a merge -> skip repeats
            if sha in seen:
                continue
            seen.add(sha)
            commit = c.get("commit", {})
            author = commit.get("author") or {}
            out.append({
                "hash": sha,
                "short_hash": sha[:8],
                "message": (commit.get("message") or "").strip(),
                "author": author.get("name", ""),
                "date": author.get("date", ""),
                "branch": branch,
                "url": c.get("html_url", ""),
            })

    # Newest commits first
    out.sort(key=lambda c: c["date"], reverse=True)
    return out


# Read pull requests (open, closed and merged)
def fetch_prs(repo: str | None = None, limit: int = 50) -> list[dict]:
    repo = _repo(repo)
    r = requests.get(
        f"{API}/repos/{repo}/pulls",
        headers=_headers(),
        params={"state": "all", "per_page": limit, "sort": "updated", "direction": "desc"},
        timeout=15,
    )
    r.raise_for_status()
    out = []
    for p in r.json():
        # GitHub only says open/closed; a merged_at date means it was merged
        merged = bool(p.get("merged_at"))
        out.append({
            "number": p["number"],
            "title": p.get("title", ""),
            "state": "merged" if merged else p.get("state", ""),  # open / closed / merged
            "branch": (p.get("head") or {}).get("ref", ""),
            "author": (p.get("user") or {}).get("login", ""),
            "merged": merged,
            "created_at": p.get("created_at", ""),
            "updated_at": p.get("updated_at", ""),
            "url": p.get("html_url", ""),
        })
    return out


# Read the list of branch names
def fetch_branches(repo: str | None = None, limit: int = 100) -> list[str]:
    repo = _repo(repo)
    r = requests.get(
        f"{API}/repos/{repo}/branches",
        headers=_headers(),
        params={"per_page": limit},
        timeout=15,
    )
    r.raise_for_status()
    # List comprehension: take only the name of each branch
    return [b["name"] for b in r.json()]


# Put commits, PRs and branches together in one dictionary
def build_github_data(repo: str | None = None) -> dict:
    repo = _repo(repo)
    return {
        "repo": repo,
        "commits": fetch_commits(repo),
        "prs": fetch_prs(repo),
        "branches": fetch_branches(repo),
    }


if __name__ == "__main__":
    import json
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
    data = build_github_data()
    print(f"Repo: {data['repo']}")
    print(f"Commits (last 14d): {len(data['commits'])}")
    for c in data["commits"][:5]:
        print(f"  {c['short_hash']}  {c['message'].splitlines()[0][:70]}  — {c['author']}")
    print(f"PRs: {len(data['prs'])}")
    for p in data["prs"][:5]:
        print(f"  #{p['number']} [{p['state']}] {p['title'][:50]}  (branch: {p['branch']})")
    print(f"Branches: {len(data['branches'])} — {data['branches'][:8]}")
