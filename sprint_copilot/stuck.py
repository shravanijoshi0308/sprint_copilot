"""
stuck.py — Phase 8: flag work that looks stuck or at-risk.

Signals it looks for:
  1. A ticket has commits/PRs/branches but is still "To Do" — work started,
     ticket never moved (so it silently looks untouched).
  2. A ticket is "In Progress" but hasn't been updated in a while — stalled.
  3. A PR has been open too long — needs review or merge.

Returns short human-readable findings that the standup surfaces first.
"""

from datetime import datetime, timezone

# Status names that mean 'not started' (lowercase so 'To Do' = 'to do')
_NOT_STARTED = {"to do", "backlog", "open", "selected for development"}


# How many days ago was this date? None if missing or unreadable
def _days_since(iso: str | None) -> int | None:
    # No date -> unknown
    if not iso:
        return None
    try:
        # GitHub writes UTC as 'Z'; Python wants '+00:00'
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    # Broken date text -> return None instead of crashing
    except ValueError:
        return None
    # No time zone in the date? Treat it as UTC so we can subtract safely
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


# Return a list of warnings about stuck or at-risk work
def find_stuck(matched: dict, work_items: dict, stale_days: int = 3, pr_open_days: int = 3) -> list[str]:
    findings: list[str] = []

    for key, m in matched.get("matched", {}).items():
        t = m["ticket"]
        status = (t.get("status") or "").strip()
        # True if the ticket has any commit, PR or branch
        has_activity = bool(m["commits"] or m["prs"] or m["branches"])

        # 1. work started but ticket not moved
        # Warning 1: work exists but the ticket still says 'not started'
        if has_activity and status.lower() in _NOT_STARTED:
            n = len(m["commits"])
            detail = f"{n} commit(s)" if n else "a branch/PR"
            findings.append(f"{key} has {detail} but is still '{status}' — move it forward.")

        # 2. In Progress but stale
        # Warning 2: 'In Progress' with no update for `stale_days` days
        if status.lower() == "in progress":
            d = _days_since(t.get("updated"))
            # No date -> no check. A number -> compare with the limit
            if d is not None and d >= stale_days:
                findings.append(f"{key} is 'In Progress' but hasn't updated in {d} day(s) — stalled?")

    # 3. PRs open too long
    # Warning 3: pull request open too long (needs review/merge)
    for p in work_items.get("prs", []):
        if p.get("state") == "open":
            d = _days_since(p.get("updated_at") or p.get("created_at"))
            if d is not None and d >= pr_open_days:
                findings.append(f"PR #{p['number']} '{p['title']}' has been open {d} day(s) — needs review/merge.")

    return findings


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from dotenv import load_dotenv
    from sprint_copilot import match as matcher

    load_dotenv(Path(__file__).parent.parent / ".env")
    wi = matcher._SAMPLE if "--sample" in sys.argv else matcher.build_work_items()
    findings = find_stuck(matcher.match(wi), wi)
    print("Stuck / at-risk:" if findings else "Nothing looks stuck.")
    for f in findings:
        print("  ⚠️ " + f)
