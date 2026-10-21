"""
run.py — Phase 9: the whole Sprint Copilot flow in one command.

    read GitHub + Jira → match → move merged tickets → write standup → Slack

Flags:
    --apply      actually move tickets (default: dry-run, nothing changes)
    --no-slack   build the standup but don't post it
    --sample     run on demo data instead of live GitHub/Jira

Examples:
    python -m sprint_copilot.run                 # safe: dry-run moves, posts standup
    python -m sprint_copilot.run --apply         # live demo: really moves tickets
    python -m sprint_copilot.run --sample --apply --no-slack
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

from sprint_copilot import match as matcher
from sprint_copilot.automate import auto_move_merged
from sprint_copilot.standup import generate_standup
from sprint_copilot.slack import post_message
from datetime import date


# The whole agent in one command: sense -> match -> act -> think -> tell
def run(sample: bool = False, apply: bool = False, post_to_slack: bool = True) -> None:
    print("Sprint Copilot — full run")
    print("=" * 55)

    # 1. Sense: read GitHub + Jira (or demo data with --sample)
    work_items = matcher._SAMPLE if sample else matcher.build_work_items()
    print(f"1. Read GitHub + Jira — {len(work_items.get('commits', []))} commits, "
          f"{len(work_items.get('prs', []))} PRs, {len(work_items.get('tickets', []))} tickets")

    # 2. Match: link commits / PRs to their tickets
    matched = matcher.match(work_items)
    linked = sum(1 for m in matched["matched"].values() if m["commits"] or m["prs"] or m["branches"])
    print(f"2. Matched — {linked} ticket(s) linked to code activity")

    # 3. Act: move tickets with a merged PR to Done (dry-run unless --apply)
    print(f"3. Auto-move merged tickets {'(APPLYING)' if apply else '(dry-run)'}:")
    for line in auto_move_merged(work_items, dry_run=not apply, offline=sample):
        print(f"     {line}")

    # 4. Think: read again (statuses may have changed), then the AI writes the standup
    fresh = matcher._SAMPLE if sample else matcher.build_work_items()
    standup, _ = generate_standup(fresh)
    print("4. Standup written")

    # 5. Tell: post the standup to Slack (unless --no-slack)
    if post_to_slack:
        header = f":sunrise: *Sprint Copilot — Daily Standup ({date.today().isoformat()})*\n\n"
        post_message(header + standup)
        print("5. Posted to Slack ✅")
    else:
        print("5. Slack skipped (--no-slack)")

    print("=" * 55)
    print(standup)


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent.parent / ".env")
    run(
        # Each flag: did the user type this word in the terminal? True/False
        sample="--sample" in sys.argv,
        apply="--apply" in sys.argv,
        post_to_slack="--no-slack" not in sys.argv,
    )
