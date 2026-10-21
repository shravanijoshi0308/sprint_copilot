"""Tests for match.py: linking GitHub activity to Jira tickets by ticket key.
No network or API keys needed: they use the built-in demo data."""
from sprint_copilot import match as matcher


def test_extract_keys_finds_ticket_keys():
    """Finds ticket keys like SCRUM-1 in commit messages and branch names."""
    keys = matcher.extract_keys("SCRUM-1 add login", "feature/SCRUM-22-hr")
    assert keys == {"SCRUM-1", "SCRUM-22"}


def test_extract_keys_ignores_text_without_keys():
    """Returns nothing for text that has no ticket key."""
    assert matcher.extract_keys("tidy up readme", "", None) == set()


def test_match_links_commits_prs_and_branches():
    """Links a ticket to its commit, pull request and branch."""
    result = matcher.match(matcher._SAMPLE)
    scrum1 = result["matched"]["SCRUM-1"]
    assert [c["hash"] for c in scrum1["commits"]] == ["aaa1"]
    assert [p["number"] for p in scrum1["prs"]] == [4]
    assert "feature/SCRUM-1-login" in scrum1["branches"]


def test_unmatched_activity_is_collected():
    """Commits and pull requests without a ticket go to the 'unmatched' list."""
    result = matcher.match(matcher._SAMPLE)
    assert [c["hash"] for c in result["unmatched_commits"]] == ["ccc3"]
    assert [p["number"] for p in result["unmatched_prs"]] == [5]


def test_key_for_unknown_ticket_is_not_linked():
    """Text that only looks like a key (UTF-8) is not linked to anything."""
    # "UTF-8" looks like a ticket key to the regex, but no such ticket exists.
    data = dict(matcher._SAMPLE, commits=[
        {"hash": "x1", "short_hash": "x1", "message": "fix UTF-8 encoding", "author": "A"}])
    result = matcher.match(data)
    assert [c["hash"] for c in result["unmatched_commits"]] == ["x1"]


def test_manual_link_is_applied(tmp_path, monkeypatch):
    """A commit linked by hand shows up under the chosen ticket."""
    # Use a temporary file so the test never touches the real manual_links.json.
    monkeypatch.setattr(matcher, "_LINKS_FILE", tmp_path / "links.json")
    matcher.save_manual_link("ccc3", "SCRUM-2")
    result = matcher.match(matcher._SAMPLE)
    assert [c["hash"] for c in result["matched"]["SCRUM-2"]["commits"]] == ["ccc3"]
    assert result["unmatched_commits"] == []
