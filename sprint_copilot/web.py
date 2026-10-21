"""
web.py — a small browser dashboard for Sprint Copilot.

It shows the same flow as run.py, but on a web page:
  - the sprint tickets, their status and the work linked to them
  - anything that looks stuck
  - commits the agent could not link, which you can link by hand
  - buttons to preview or really run the agent

Run:   python -m sprint_copilot.web
Open:  http://localhost:5050            (real GitHub + Jira data)
       http://localhost:5050/?sample=1  (demo data, safe to click everything)
       http://localhost:5050/tests      (run the automated tests)

There is no login, so only run it on your own machine.
"""

import ast
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request

# Load the secret keys from .env before the other modules need them
load_dotenv(Path(__file__).parent.parent / ".env")

from sprint_copilot import jira, match as matcher
from sprint_copilot.automate import auto_move_merged, evidence_comment
from sprint_copilot.slack import post_message
from sprint_copilot.standup import build_digest, generate_standup
from sprint_copilot.stuck import find_stuck

# Flask = a small web framework: it turns Python functions into web pages
app = Flask(__name__)

# The statuses you can choose in the dropdown
STATUSES = ["To Do", "In Progress", "In Review", "Done"]

# Shared look for every page: calm colours, lots of space, one accent colour
BASE_STYLE = """
<style>
  :root { --bg:#f6f5f2; --card:#ffffff; --line:#e4e2dc; --text:#2b2b2b;
          --muted:#7a776f; --accent:#3f6e8c; --soft:#eef3f6; --warn:#a4622b; --warnbg:#fbf3ea;
          --ok:#4c7a5a; --okbg:#eef5ef; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:15px/1.55 -apple-system, "Segoe UI", system-ui, sans-serif; }
  .wrap { max-width:1080px; margin:0 auto; padding:32px 24px 60px; }
  header { display:flex; align-items:baseline; justify-content:space-between; margin-bottom:6px; }
  h1 { font-size:22px; font-weight:600; margin:0; }
  nav a { color:var(--muted); text-decoration:none; margin-left:20px; padding-bottom:3px; }
  nav a.on { color:var(--text); border-bottom:2px solid var(--accent); }
  .sub { color:var(--muted); margin-bottom:28px; }
  .sub a { color:var(--accent); }
  .grid { display:grid; grid-template-columns:1.3fr 1fr; gap:24px; align-items:start; }
  @media (max-width:820px) { .grid { grid-template-columns:1fr; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:20px 22px; margin-bottom:24px; }
  .card h2 { font-size:13px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
             color:var(--muted); margin:0 0 14px; }
  .item { border-top:1px solid var(--line); padding:14px 0; }
  .item:first-of-type { border-top:0; padding-top:0; }
  .key { font-weight:600; color:var(--accent); }
  .pill { font-size:12px; padding:2px 9px; border-radius:20px; margin-left:8px;
          background:var(--soft); color:var(--accent); }
  .pill.done { background:var(--okbg); color:var(--ok); }
  .pill.todo { background:#f1f0ec; color:var(--muted); }
  .who { color:var(--muted); }
  .link { color:var(--muted); font-size:13px; margin:6px 0 0 2px; }
  .row { margin-top:10px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  select { font:inherit; font-size:13px; padding:5px 8px; border:1px solid var(--line);
           border-radius:6px; background:#fff; color:var(--text); }
  button { font:inherit; font-size:13px; padding:6px 12px; border-radius:6px; cursor:pointer;
           border:1px solid var(--line); background:#fff; color:var(--text); }
  button:hover { border-color:var(--accent); }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; padding:9px 16px; }
  .note { color:var(--muted); font-size:13px; }
  .warn { background:var(--warnbg); color:var(--warn); border-radius:8px;
          padding:10px 14px; margin-bottom:8px; font-size:14px; }
  pre { white-space:pre-wrap; background:#faf9f7; border:1px solid var(--line);
        border-radius:8px; padding:14px; font-size:13px; line-height:1.5; }
</style>
"""

# The dashboard page. {{ ... }} and {% ... %} are filled in by Flask (Jinja templates)
DASHBOARD = """<!doctype html>
<html><head><meta charset="utf-8"><title>Sprint Copilot</title>""" + BASE_STYLE + """</head>
<body><div class="wrap">
  <header>
    <h1>Sprint Copilot</h1>
    <nav><a class="on" href="/{{ '?sample=1' if sample else '' }}">Dashboard</a>
         <a href="/tests">Tests</a></nav>
  </header>
  <div class="sub">
    Repository: {{ repo }} &middot; {{ 'demo data' if sample else 'live GitHub and Jira data' }}
    &middot; <a href="/?sample={{ 0 if sample else 1 }}">switch to {{ 'live' if sample else 'demo' }} data</a>
  </div>

  {% if stuck %}
  <div class="card">
    <h2>Needs attention</h2>
    {% for s in stuck %}<div class="warn">{{ s }}</div>{% endfor %}
  </div>
  {% endif %}

  <div class="grid">
    <div class="card">
      <h2>Tickets and linked work</h2>
      {% for t in tickets %}
      <div class="item">
        <span class="key">{{ t.key }}</span>
        <span class="pill {{ t.cls }}">{{ t.status }}</span>
        &nbsp;{{ t.title }} <span class="who">&middot; {{ t.assignee }}</span>
        {% for l in t.links %}<div class="link">{{ l }}</div>{% endfor %}
        {% if not t.links %}<div class="link">No linked commits or pull requests yet</div>{% endif %}
        <div class="row">
          <select id="sel-{{ t.key }}">
            {% for s in statuses %}<option {{ 'selected' if t.status == s else '' }}>{{ s }}</option>{% endfor %}
          </select>
          <button onclick="move('{{ t.key }}')">Set status</button>
          <span id="msg-{{ t.key }}" class="note"></span>
        </div>
      </div>
      {% endfor %}
    </div>

    <div>
      <div class="card">
        <h2>Commits without a ticket</h2>
        {% for c in unmatched %}
        <div class="item">
          <span class="note">{{ c.short_hash }}</span> {{ c.message.split('\\n')[0][:60] }}
          <div class="row">
            <select id="lnk-{{ c.hash }}">{% for k in keys %}<option>{{ k }}</option>{% endfor %}</select>
            <button onclick="link('{{ c.hash }}')">Link to ticket</button>
            <span id="lmsg-{{ c.hash }}" class="note"></span>
          </div>
        </div>
        {% endfor %}
        {% if not unmatched %}<div class="note">Every commit is linked to a ticket.</div>{% endif %}
      </div>

      <div class="card">
        <h2>Run the agent</h2>
        <p class="note">Reads GitHub and Jira, moves tickets with a merged pull request to Done,
           writes the standup and posts it to Slack.</p>
        <div class="row">
          <button onclick="run(false)">Preview (nothing changes)</button>
          <button class="primary" onclick="run(true)">Run for real</button>
        </div>
        <div id="out"></div>
      </div>
    </div>
  </div>
</div>

<script>
// Each function sends a small request to the Python server and shows the answer.
async function post(url, body) {
  const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                              body: JSON.stringify(body)});
  return r.json();
}
async function move(key) {
  const msg = document.getElementById('msg-' + key);
  msg.textContent = 'Saving...';
  const d = await post('/move', {key: key, status: document.getElementById('sel-' + key).value,
                                 sample: {{ 'true' if sample else 'false' }}});
  msg.textContent = d.msg;
}
async function link(hash) {
  const msg = document.getElementById('lmsg-' + hash);
  msg.textContent = 'Saving...';
  const d = await post('/link', {commit: hash, ticket: document.getElementById('lnk-' + hash).value});
  msg.textContent = d.msg;
}
async function run(apply) {
  if (apply && !confirm('This will really move tickets and post to Slack. Continue?')) return;
  const out = document.getElementById('out');
  out.innerHTML = '<p class="note">Working...</p>';
  const d = await post('/run', {apply: apply, sample: {{ 'true' if sample else 'false' }}});
  out.innerHTML = '<h2 style="margin-top:18px">What happened</h2><pre>' + d.actions.join('\\n') + '</pre>'
                + '<h2>Standup' + (apply ? ' (posted to Slack)' : ' (preview)') + '</h2><pre>' + d.standup + '</pre>';
}
</script>
</body></html>
"""

# CSS class for each status pill
_CLS = {"to do": "todo", "in progress": "", "in review": "", "done": "done"}


def _view(sample: bool):
    """Collect everything the dashboard shows: tickets, links, stuck work, unlinked commits."""
    # Demo data or real data from GitHub + Jira
    wi = matcher._SAMPLE if sample else matcher.build_work_items()
    matched = matcher.match(wi)
    stuck = find_stuck(matched, wi)

    tickets = []
    for key, m in matched["matched"].items():
        t = m["ticket"]
        # One readable line for each linked PR, commit and branch
        links = [f"Pull request #{p['number']} ({p['state']}): {p['title']}" for p in m["prs"]]
        links += [f"Commit {c['short_hash']}: {c['message'].splitlines()[0][:60]}" for c in m["commits"]]
        links += [f"Branch {b}" for b in m["branches"]]
        tickets.append({
            "key": key, "title": t["title"], "status": t["status"],
            "assignee": t.get("assignee", ""), "links": links,
            "cls": _CLS.get(t["status"].lower(), ""),
        })
    keys = list(matched["matched"].keys())
    unmatched = matched["unmatched_commits"][:20]  # show at most 20
    return wi, tickets, stuck, unmatched, keys


# Main page: http://localhost:5050
@app.route("/")
def dashboard():
    sample = request.args.get("sample") == "1"
    wi, tickets, stuck, unmatched, keys = _view(sample)
    return render_template_string(DASHBOARD, repo=wi["repo"], tickets=tickets, stuck=stuck,
                                  unmatched=unmatched, keys=keys, sample=sample, statuses=STATUSES)


# Human override 1: link a commit to a ticket by hand (saved in manual_links.json)
@app.route("/link", methods=["POST"])
def link():
    data = request.get_json(force=True)
    matcher.save_manual_link(data["commit"], data["ticket"])
    return jsonify({"ok": True, "msg": f"Linked to {data['ticket']}. Reload the page to see it."})


# Human override 2: set a ticket's status by hand, and leave an evidence comment
@app.route("/move", methods=["POST"])
def move():
    data = request.get_json(force=True)
    key, status = data["key"], data["status"]

    # In demo mode there is no real Jira board, so only report what would happen
    if data.get("sample"):
        return jsonify({"ok": True, "msg": f"Demo mode: {key} would move to {status}."})

    ok, msg = jira.move_issue(key, status, dry_run=False)
    if ok:
        try:
            # Cite this ticket's real linked PRs and commits in the comment
            m = matcher.match(matcher.build_work_items())["matched"].get(key, {"prs": [], "commits": []})
            jira.add_comment(key, evidence_comment(m, status), dry_run=False)
            msg += " and comment added"
        except Exception as exc:
            msg += f" (comment failed: {exc})"
    return jsonify({"ok": ok, "msg": msg})


# Run the whole flow: preview (dry run) or for real
@app.route("/run", methods=["POST"])
def run():
    data = request.get_json(force=True)
    apply, sample = bool(data.get("apply")), bool(data.get("sample"))

    wi = matcher._SAMPLE if sample else matcher.build_work_items()
    # Demo data never touches real Jira, even when "Run for real" is clicked
    actions = auto_move_merged(wi, dry_run=not apply, offline=sample)

    # Read again, because the moves may have changed ticket statuses
    fresh = matcher._SAMPLE if sample else matcher.build_work_items()
    try:
        standup, _ = generate_standup(fresh)
    except Exception as exc:
        # No AI keys (or the AI is down): show the collected facts instead
        digest = build_digest(matcher.match(fresh), fresh)
        standup = (f"The AI could not write the standup ({type(exc).__name__}). "
                   f"Check the AI keys in .env. These are the facts it would have used:\n\n{digest}")

    if apply and not sample:
        post_message(f":sunrise: *Sprint Copilot daily standup ({date.today().isoformat()})*\n\n" + standup)
    return jsonify({"actions": actions, "standup": standup})


# ── Tests page ────────────────────────────────────────────────────────────────

# The project folder (one level above sprint_copilot/), where the tests/ folder lives
PROJECT_ROOT = Path(__file__).parent.parent

TESTS_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Sprint Copilot tests</title>""" + BASE_STYLE + """
<style>
  .summary { font-size:17px; margin:4px 0 0; }
  .t { display:flex; gap:14px; align-items:flex-start; border-top:1px solid var(--line); padding:12px 0; }
  .t:first-of-type { border-top:0; }
  .mark { flex:none; width:64px; text-align:center; font-size:12px; font-weight:600;
          border-radius:20px; padding:3px 0; }
  .mark.pass { background:var(--okbg); color:var(--ok); }
  .mark.fail { background:var(--warnbg); color:var(--warn); }
  .mark.wait { background:#f1f0ec; color:var(--muted); }
  .name { font-family:ui-monospace, Menlo, monospace; font-size:12px; color:var(--muted); }
  .file { font-size:13px; font-weight:600; color:var(--muted); margin:18px 0 4px; text-transform:uppercase; letter-spacing:.05em; }
</style></head>
<body><div class="wrap">
  <header>
    <h1>Sprint Copilot</h1>
    <nav><a href="/?sample=1">Dashboard</a><a class="on" href="/tests">Tests</a></nav>
  </header>
  <div class="sub">Runs <code>pytest</code> on this computer. The tests use demo data and fake Jira calls,
    so they need no API keys.</div>

  <div class="card">
    <div class="row" style="justify-content:space-between">
      <div><h2 style="margin:0">Result</h2><p class="summary" id="summary">Not run yet.</p></div>
      <button class="primary" onclick="runTests()">Run tests</button>
    </div>
  </div>

  <div class="card">
    <h2>Tests</h2>
    {% for file, tests in groups %}
      <div class="file">{{ file }}</div>
      {% for t in tests %}
      <div class="t">
        <span class="mark wait" id="m-{{ t.name }}">waiting</span>
        <div><div>{{ t.doc }}</div><div class="name">{{ t.name }}</div></div>
      </div>
      {% endfor %}
    {% endfor %}
  </div>

  <div class="card" id="details" style="display:none">
    <h2>Full pytest output</h2><pre id="output"></pre>
  </div>
</div>
<script>
async function runTests() {
  document.getElementById('summary').textContent = 'Running...';
  document.querySelectorAll('.mark').forEach(m => { m.className = 'mark wait'; m.textContent = 'running'; });
  const r = await fetch('/tests/run', {method: 'POST'});
  const d = await r.json();
  for (const [name, outcome] of Object.entries(d.results)) {
    const m = document.getElementById('m-' + name);
    if (!m) continue;
    const ok = outcome === 'PASSED';
    m.className = 'mark ' + (ok ? 'pass' : 'fail');
    m.textContent = ok ? 'passed' : outcome.toLowerCase();
  }
  document.getElementById('summary').textContent = d.summary;
  document.getElementById('output').textContent = d.output;
  document.getElementById('details').style.display = 'block';
}
</script>
</body></html>
"""


def _list_tests() -> list[tuple[str, list[dict]]]:
    """Read the tests/ folder and list every test with its one-line description (docstring)."""
    groups = []
    for path in sorted((PROJECT_ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text())
        tests = [
            {"name": node.name, "doc": ast.get_docstring(node) or node.name}
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
        # "test_match.py" -> "match"
        groups.append((path.stem.removeprefix("test_"), tests))
    return groups


# Tests page: http://localhost:5050/tests
@app.route("/tests")
def tests_page():
    return render_template_string(TESTS_PAGE, groups=_list_tests())


# Run pytest in a separate process and send back the result of each test
@app.route("/tests/run", methods=["POST"])
def run_tests():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    output = proc.stdout + proc.stderr

    # Lines look like: tests/test_match.py::test_name PASSED   [ 10%]
    results = {name: outcome for name, outcome in
               re.findall(r"::(\w+) (PASSED|FAILED|ERROR|SKIPPED)", output)}

    # Last summary line, e.g. "16 passed in 0.20s"
    summary_match = re.findall(r"=+ (.+ in [\d.]+s.*?) =+", output)
    summary = summary_match[-1] if summary_match else "Could not read the pytest summary."
    return jsonify({"results": results, "summary": summary, "output": output})


if __name__ == "__main__":
    # Port 5050, because 5000 is used by AirPlay on macOS.
    # 127.0.0.1 = only reachable from this computer (there is no login).
    port = int(os.environ.get("PORT", 5050))
    print(f"Sprint Copilot dashboard: http://localhost:{port}   (demo data: /?sample=1, tests: /tests)")
    app.run(host="127.0.0.1", port=port, debug=False)
