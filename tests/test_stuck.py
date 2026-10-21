"""Tests for stuck.py: flagging work that looks stuck or at risk."""
from datetime import datetime, timedelta, timezone

from sprint_copilot import match as matcher
from sprint_copilot.stuck import find_stuck


def _days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _data(status, updated=None, prs=None):
    return {
        "repo": "demo/repo",
        "tickets": [{"key": "SCRUM-1", "title": "Login", "status": status,
                     "assignee": "Alex", "updated": updated}],
        "commits": [{"hash": "a1", "short_hash": "a1", "message": "SCRUM-1 login form", "author": "Alex"}],
        "prs": prs or [],
        "branches": [],
    }


def test_flags_ticket_with_work_but_still_to_do():
    """Warns when a ticket has work but still says 'To Do'."""
    wi = _data("To Do")
    findings = find_stuck(matcher.match(wi), wi)
    assert any("still 'To Do'" in f for f in findings)


def test_flags_in_progress_ticket_not_updated_for_days():
    """Warns when an 'In Progress' ticket has not changed for days."""
    wi = _data("In Progress", updated=_days_ago(5))
    findings = find_stuck(matcher.match(wi), wi)
    assert any("hasn't updated in 5 day(s)" in f for f in findings)


def test_recently_updated_ticket_is_not_flagged():
    """Does not warn about a ticket that was updated recently."""
    wi = _data("In Progress", updated=_days_ago(1))
    assert find_stuck(matcher.match(wi), wi) == []


def test_flags_pr_open_too_long():
    """Warns when a pull request has been open too long."""
    pr = {"number": 7, "title": "SCRUM-1 login", "state": "open", "branch": "feature/SCRUM-1",
          "merged": False, "updated_at": _days_ago(4)}
    wi = _data("In Progress", updated=_days_ago(0), prs=[pr])
    findings = find_stuck(matcher.match(wi), wi)
    assert any("PR #7" in f for f in findings)


def test_date_without_timezone_does_not_crash():
    """A date without a time zone is read as UTC instead of crashing."""
    from sprint_copilot.stuck import _days_since
    assert _days_since("2026-10-01T10:00:00") is not None
