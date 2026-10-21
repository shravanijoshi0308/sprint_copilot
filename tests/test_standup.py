"""Tests for standup.py: the text handed to the LLM (no LLM call is made)."""
from sprint_copilot import match as matcher
from sprint_copilot.standup import build_digest


def test_digest_groups_work_per_person():
    """The facts for the AI are grouped per person."""
    wi = matcher._SAMPLE
    digest = build_digest(matcher.match(wi), wi)
    assert "## Person: Alex" in digest
    assert "## Person: Shravani" in digest
    assert "SCRUM-1 add login form" in digest
    assert "Open PRs: 1" in digest
