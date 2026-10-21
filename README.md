# Sprint Copilot

![Tests](https://github.com/shravanijoshi0308/sprint_copilot/actions/workflows/tests.yml/badge.svg)

Sprint Copilot is a small AI agent that takes over the routine coordination work a scrum master does every morning.

It looks at what the team did in GitHub, connects that work to the right Jira tickets, moves finished tickets to Done, points out work that seems stuck, and posts a short daily standup to Slack.

## Why I built it

In my previous job I worked in agile teams for almost three years. A surprising amount of time went into keeping the board up to date: checking who worked on what, moving tickets that were already finished, and collecting updates for the standup. All of that information already exists in GitHub and Jira. It just needs to be read and put together.

Sprint Copilot started as a hackathon project. I kept developing it afterwards, added tests and continuous integration, and used it to learn more about building agents that act on real tools safely.

## How it works

The agent follows five steps:

1. **Read.** `github.py` reads commits, pull requests and branches. `jira.py` reads the sprint's tickets.
2. **Match.** `match.py` finds ticket keys such as `SCRUM-1` in commit messages, pull request titles and branch names, and links each piece of work to its ticket.
3. **Act.** `automate.py` moves a ticket to Done when its pull request has been merged, and leaves a comment on the ticket with links to the pull request and commits.
4. **Think.** `stuck.py` flags work that looks stuck. `standup.py` collects the facts for each person, and `llm.py` asks a language model to turn those facts into a readable standup.
5. **Tell.** `slack.py` posts the standup to a Slack channel.

`run.py` runs all five steps with one command. `web.py` offers the same flow as a small dashboard in the browser, where you can also correct links and ticket statuses by hand. `check_setup.py` checks that every API key works before you start.

## Keeping it safe

The agent changes a real Jira board that a whole team relies on, so a few rules are built in:

- **Dry run by default.** Without the `--apply` flag, the agent only reports what it would change.
- **Evidence on every change.** Each automatic move leaves a comment explaining why, with links.
- **A human can always override.** Unlinked commits and wrong statuses can be fixed by hand in the dashboard.
- **The model only rewrites facts.** All data is collected in plain Python first. The prompt tells the model to use only that data and never invent work, which keeps the standup honest.
- **Secrets stay out of the code.** API keys live in a local `.env` file that is never committed.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in your own keys

python -m sprint_copilot.check_setup               # check the keys
python -m sprint_copilot.run --sample --no-slack   # demo data, nothing is posted
python -m sprint_copilot.run                       # real data, moves are only previewed
python -m sprint_copilot.run --apply               # real data, tickets are really moved
python -m sprint_copilot.web                       # dashboard on http://localhost:5050
```

## Tests

```bash
pip install pytest
pytest -v
```

The tests cover ticket-key matching, stuck-work detection, the automatic ticket moves and the standup input. They use built-in demo data and replace the Jira calls with fakes, so they need no API keys or internet connection.

GitHub Actions runs the tests automatically on every push and pull request. The workflow is in `.github/workflows/tests.yml`.

## What I would improve next

- Handle dates without a time zone in `stuck.py`, which currently cause an error.
- Add pagination so large repositories with more than 100 branches or pull requests are read completely.
- Add a login to the dashboard before using it with a real team.
- Map GitHub and Jira users explicitly instead of matching by first name.
- Run the agent on a schedule so the standup is posted every morning automatically.

## How it was built

I designed Sprint Copilot and built it with AI-assisted development using Claude Code. I made the decisions about the architecture and the safety rules, and I tested and reviewed every part.
