"""
standup.py — Phase 5: write an honest, per-person daily standup with the LLM.

Takes the matched GitHub+Jira data (match.py) and produces a short standup
grouped by person: what they did (from commits/PRs), the status of their
tickets, and any blockers — with a hard rule that it never invents work and
says plainly when someone was quiet.

People are grouped by first name so a git author ("Alex") and a Jira
assignee ("Alex Weber") land together. PRs are reported at the team level
(GitHub logins don't map cleanly to git/Jira names).
"""

from collections import defaultdict

from sprint_copilot.llm import llm
from sprint_copilot import match as matcher
from sprint_copilot.stuck import find_stuck

# The AI's rules (system prompt): use ONLY the given facts -> no hallucination
SYSTEM_PROMPT = """You write a team's daily standup from real activity data \
(git commits, pull requests, Jira tickets). Be honest and specific.

Hard rules:
- Use ONLY the activity provided. Never invent tasks, progress, or blockers.
- Put blockers / at-risk items FIRST if there are any.
- If a person has little or no activity, say so plainly (e.g. "No tracked
  activity today") — do not pad with filler for people who did nothing.
- For people who DID work, be concrete and detailed: write 3-6 bullets under
  "Did" that name the actual features, files, modules, or areas from their
  commit messages. Prefer specifics ("added the Slack posting module and the
  auto-move-on-merge logic; fixed the GitHub reader to scan all branches")
  over vague summaries ("made progress on several phases"). Group closely
  related commits, but don't collapse real detail into one vague line.

Output (markdown), one block per person:
*<Name>*
• Did:
   - <concrete bullet naming what was built/changed>
   - <another>
   - ... (3-6 for an active person)
• Tickets: <their tickets with status, or "none assigned">
• Blockers: <only if evident from the data, else "None">

End with a one-line *Team* note: open PRs waiting, and anything unassigned
that has activity.
"""


# 'Alex Weber' and 'Alex' -> 'alex', so Git and Jira names match
def _first(name: str) -> str:
    name = (name or "").strip()
    return name.split()[0].lower() if name else ""


# Collect the FACTS per person in plain Python (no AI here)
def build_digest(matched: dict, work_items: dict) -> str:
    """Assemble the text handed to the LLM."""
    # defaultdict: creates an empty box automatically for each new person
    people: dict[str, dict] = defaultdict(lambda: {"name": "", "commits": [], "tickets": []})

    for c in work_items.get("commits", []):
        k = _first(c.get("author", ""))
        if not k:
            continue
        p = people[k]
        # Keep the longer (fuller) version of the name
        p["name"] = max(p["name"], c["author"], key=len)
        p["commits"].append(c)

    for t in work_items.get("tickets", []):
        a = t.get("assignee", "")
        if not a or a == "Unassigned":
            continue
        k = _first(a)
        p = people[k]
        p["name"] = max(p["name"], a, key=len)
        p["tickets"].append(t)

    lines = [f"Repo: {work_items.get('repo', '')}", ""]

    # Stuck / at-risk items go at the TOP
    stuck = find_stuck(matched, work_items)
    if stuck:
        lines.append("## STUCK / AT RISK (surface these first)")
        for s in stuck:
            lines.append(f"  - {s}")
        lines.append("")

    for _, p in people.items():
        lines.append(f"## Person: {p['name']}")
        if p["commits"]:
            lines.append(f"Commits ({len(p['commits'])}) — full messages for detail:")
            # At most 20 commits per person, each cut to 240 characters (keeps the AI input short)
            for c in p["commits"][:20]:
                # flatten the whole message (subject + body) so the LLM has
                # the real substance, not just a truncated first line
                full = " ".join(c["message"].split())
                lines.append(f"  - {full[:240]}")
        else:
            lines.append("Commits: none")
        if p["tickets"]:
            lines.append("Assigned tickets:")
            for t in p["tickets"]:
                lines.append(f"  - {t['key']} [{t['status']}] {t['title']}")
        else:
            lines.append("Assigned tickets: none")
        lines.append("")

    open_prs = [p for p in work_items.get("prs", []) if p.get("state") == "open"]
    merged_prs = [p for p in work_items.get("prs", []) if p.get("merged")]
    lines.append("## Team")
    lines.append(f"Open PRs: {len(open_prs)}" + (": " + ", ".join(f"#{p['number']} {p['title']}" for p in open_prs) if open_prs else ""))
    lines.append(f"Recently merged PRs: {len(merged_prs)}")

    # Tickets that have linked activity but nobody assigned.
    # Tickets with work but nobody assigned
    unassigned_active = [
        key for key, m in matched.get("matched", {}).items()
        if (m["commits"] or m["prs"]) and m["ticket"].get("assignee") in ("", "Unassigned")
    ]
    if unassigned_active:
        lines.append(f"Unassigned tickets with activity: {', '.join(unassigned_active)}")

    return "\n".join(lines)


# match -> digest -> AI writes the standup. Returns (standup, digest)
def generate_standup(work_items: dict | None = None) -> tuple[str, str]:
    """Returns (standup_text, digest). Builds real data if none passed."""
    if work_items is None:
        work_items = matcher.build_work_items()
    matched = matcher.match(work_items)
    digest = build_digest(matched, work_items)
    # The only AI call: rules + facts in, standup text out
    standup = llm(SYSTEM_PROMPT, digest, max_tokens=1200)
    return standup, digest


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")

    if "--sample" in sys.argv:
        wi = matcher._SAMPLE
    else:
        wi = matcher.build_work_items()

    if "--digest" in sys.argv:
        # Show the exact text sent to the LLM (no API call).
        print(build_digest(matcher.match(wi), wi))
    else:
        standup, _ = generate_standup(wi)
        print("=" * 60)
        print(standup)
        print("=" * 60)
