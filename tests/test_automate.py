"""Tests for automate.py: moving tickets to Done when their PR is merged.
Jira calls are replaced with fakes, so nothing real is changed."""
from sprint_copilot import automate, match as matcher


def test_evidence_comment_lists_prs_and_commits():
    """The Jira comment lists the pull request and commit links."""
    m = {"prs": [{"number": 4, "title": "SCRUM-1 login", "url": "https://x/pr/4"}],
         "commits": [{"short_hash": "aaa1", "message": "SCRUM-1 add login form", "url": ""}]}
    text = automate.evidence_comment(m, "Done")
    assert "moved to Done" in text
    assert "PR #4" in text and "https://x/pr/4" in text
    assert "commit aaa1" in text


def test_evidence_comment_without_links():
    """The Jira comment says so when there is nothing to link."""
    assert "no linked commits or PRs" in automate.evidence_comment({}, "Done")


def test_only_tickets_with_merged_prs_are_moved(monkeypatch):
    """Only tickets with a merged pull request are moved to Done."""
    moved, commented = [], []
    monkeypatch.setattr(automate.jira, "move_issue",
                        lambda key, status, dry_run=True: (moved.append(key) or True, f"{key} -> {status}"))
    monkeypatch.setattr(automate.jira, "add_comment",
                        lambda key, text, dry_run=True: (commented.append(key) or True, "comment added"))

    automate.auto_move_merged(matcher._SAMPLE, dry_run=True)

    # In the demo data only SCRUM-1 has a merged PR (#4).
    assert moved == ["SCRUM-1"]
    assert commented == ["SCRUM-1"]


def test_ticket_already_done_is_skipped(monkeypatch):
    """A ticket that is already Done is not moved again."""
    monkeypatch.setattr(automate.jira, "move_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not move")))
    data = dict(matcher._SAMPLE)
    data["tickets"] = [dict(t, status="Done") if t["key"] == "SCRUM-1" else t for t in data["tickets"]]
    lines = automate.auto_move_merged(data, dry_run=True)
    assert any("already 'Done'" in line for line in lines)


def test_offline_mode_never_calls_jira(monkeypatch):
    """Demo mode never contacts the real Jira."""
    # Demo mode must work without any Jira account.
    monkeypatch.setattr(automate.jira, "move_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Jira was called")))
    lines = automate.auto_move_merged(matcher._SAMPLE, dry_run=False, offline=True)
    assert lines == ["SCRUM-1: WOULD move -> Done   (merged PR #4, demo mode)"]
