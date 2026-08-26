# verified-ops-starter

**Your scheduled job says `exit 0`. Prove it did the work.**

[![selftest](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter/actions/workflows/selftest.yml/badge.svg)](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter/actions/workflows/selftest.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](#requirements)
[![deps: none](https://img.shields.io/badge/dependencies-none-lightgrey.svg)](#requirements)

Three small checks, no server, no dependencies. They replace a job's *self-report*
with *evidence*:

| check | question it answers | catches | code |
|---|---|---|---|
| `freshness` | is the job's real **output** young enough? | exit 0 while the artifact rots | `verified_ops/freshness.py` |
| `wrap` | did this run actually **change** anything? | exit 0 with no work done | `verified_ops/wrap.py` |
| `rollout` | is the fix **on every box**, read back as a fact? | "rolled out" that never landed | `verified_ops/rollout.py` |

Everything speaks one [exit-code contract](#exit-code-contract), implemented once in
`verified_ops/contract.py`, in which a dead checker cannot look like a clean result.

## Why

An agent, a cron job and a nightly script all report on themselves, and the report
is the first thing to break — each failure below has its own mutant in `selftest.py`:

- the model refused, the API returned an empty page, the token expired, the filter matched
  nothing — the process still **exits 0** and stamps its heartbeat (caught by `verified_ops/wrap.py`);
- a checker written in Python dies on an unhandled exception and **exits 1** — the same code
  many checkers use for "I found a problem", so the dashboard paints the corpse yellow and
  moves on (caught by `verified_ops/contract.py`);
- the fix "was rolled out" because it was *sent*, and an offline box, a lagging box and a
  healthy box are all equally quiet (caught by `verified_ops/rollout.py`).

Heartbeat monitoring (https://healthchecks.io, cronitor, dead-man switches) answers
*did it fire?* — a genuinely different question, and worth having.
This kit answers *did the work land?* and is designed to sit next to them, not replace them.

## Quickstart (5 minutes, nothing to install)

```bash
git clone https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter
cd verified-ops-starter
python3 selftest.py        # 44 checks, every one of them broken by a mutant first
```

**1. A healthy run, then the freshness check:**

```bash
python3 examples/demo_job.py --once
python3 -m verified_ops freshness --config examples/verified-ops.json
```

```
FRESH       nightly export 0.0h
SKIPPED     dated dumps -- no such file: out/dump-*.json
```
`echo $?` → `0`.

**2. Now the failure your job will never report about itself.** `--no-op` is what a
real job does when a filter matches nothing: it prints something reassuring and exits 0.

```bash
python3 -m verified_ops wrap --artifact examples/out/export.json \
        --config examples/verified-ops.json -- python3 examples/demo_job.py --no-op
```

```
done (fetched 0 rows)
child exited 0 in 0.3s
verified-ops wrap: the job exited 0 but examples/out/export.json did not change
  (mtime 2026-08-04 05:51:42, 72 bytes) -- silent no-op
  command: python3 examples/demo_job.py --no-op
alert delivered via console
```
`echo $?` → `1` (found **and** announced).

A wrapped job that dies is red, not yellow: any non-zero child code comes back as `4`,
because a job crashing with Python's default exit 1 would otherwise land on the code that
means "found something and announced it". If one of your job's non-zero codes really is a
designed finding, declare it — `--signal 1,3` — and it passes through unchanged.

**3. Prove a fix is really on every box:**

```bash
python3 -m verified_ops rollout --config examples/verified-ops.json
```

```
fix: demo: config carries mode=verified
APPLIED      this box -- read 'mode=verified'
NOT_FOR_ME   cloud runner -- reads the mode from the environment, no local file
```

**4. Point it at your own job:** copy `examples/verified-ops.json` next to it, replace
the artifact path with the file your job rewrites on every healthy run, set
`max_age_h` to *cadence + grace* (daily job → 26), and schedule
`python3 -m verified_ops freshness --config /path/verified-ops.json` once a day.

## Exit-code contract

```
0  CLEAN        nothing wrong; evidence checked
1  FOUND        a real problem was found AND the alert was delivered
3  UNDELIVERED  a real problem was found and the alert could NOT be delivered
4  CRASHED      the checker itself died
```

Three rules give the codes teeth, all enforced in `verified_ops/contract.py`:

- **1 is only returned after delivery succeeded** (`verified_ops/alert.py`). If your pager is
  down the answer is 3, never 1 — otherwise "problem found" and "problem announced" become
  the same event. `--dry-run` returns 3 for the same reason: it announces nothing.
- **A run that measured nothing returns 4, never 0** (`verified_ops/cli.py`). An empty artifact
  list, a misspelled `artifacts` key, a rollout where every target opted out — all of them used
  to produce the cheerful zero this kit exists to stop.
- **Any uncaught exception becomes 4** (`guard` in `verified_ops/contract.py`). Wrap your own
  checkers too, it is one line:

```python
from verified_ops import guard

if __name__ == "__main__":
    sys.exit(guard(main))     # crash -> 4, so it can never hide inside your signal list
```

On your scoreboard: `1` is yellow (open finding, already announced), `3` and `4` are red.

## Config

One JSON file, `verified-ops.json` (see [`examples/`](examples/verified-ops.json)).
Relative artifact paths resolve against the config file's directory; `verify` and
`alert` commands run in your current working directory.

```jsonc
{
  "artifacts": [
    {"name": "nightly export",
     "path": "out/export.json",   // the file the job REWRITES every healthy run
     "max_age_h": 26,             // cadence + grace: one missed run is borderline, not an alarm
     "min_bytes": 2,              // optional: an empty rewrite is a silent failure too
     "contains": "\"rows\"",      // optional: a marker from the BODY, not the filename
     "cure": "python tools/export.py --once, then read out/export.log",
     "only_if_exists": false}     // optional: true -> absence is a declared non-event
  ],
  "rollout": {
    "fix": "cache TTL raised to 900s",
    "targets": [
      {"name": "hub", "verify": ["ssh", "hub", "grep -o 'ttl=[0-9]*' /etc/app.conf"],
       "expect": "ttl=900"},
      {"name": "cloud", "not_for_me": "reads the value from the environment"}
    ]
  },
  "alert": {"command": ["python3", "tools/page.py"]}   // omit for the stderr rail
}
```

Use `"newest_glob": "out/dump-*.json"` instead of `"path"` for jobs that write a new
dated file each run.

`rollout` refuses to count a target whose `verify` only exits 0 — it comes back `WEAK` and
keeps the rollout open (`check_target` in `verified_ops/rollout.py`). Exit 0 is the verify
saying *"I ran"*; `expect` is what makes it say *"the value is here"*.

`expect` is a plain substring, so `ttl=900` also matches `ttl=9000`. When the fact has
neighbours, use `"expect_regex": "\\bttl=900\\b"` instead — also `verified_ops/rollout.py`.

`wrap` takes `--timeout-s N`: a job that hangs is killed and announced (`verified_ops/wrap.py`),
because "still running" is the quietest failure a scheduler can show you.

## Traps this kit already paid for

Each one cost a real silent outage before it became a line of code or a test. The file after
each trap is where it is handled; every one has a mutant in `selftest.py`:

- **`exit 1` collides** — `verified_ops/contract.py`. Python's unhandled-exception code is the
  same code checkers use for "found something". Hence `guard()` and the 4.
- **Fresh mtime ≠ fresh work over a synced folder** — `verified_ops/freshness.py`.
  Syncthing/Dropbox/rsync stamp a new mtime while copying an *old* file onto the box, so a
  stale artifact reads green. Only point `newest_glob` at a directory your sync engine cannot touch.
- **A wide glob mask hides a stall** — `verified_ops/freshness.py`. One unrelated file landing
  in the same folder masks a dead job forever, so the tool always prints *which* file it
  measured and how many matched.
- **200 with the wrong body** — `verified_ops/freshness.py` (`NO_MARKER`). Fresh and non-empty
  is not the same as correct: that is what `contains` is for, and the marker must come from
  the body, never the filename.
- **Alert receivers that read argv as filenames** (`cat`, `curl -d @-`) — `verified_ops/alert.py`.
  They fail on the extra argument and turn a finding into an exit 3, so the alert text arrives
  on **stdin as well**; use it.
- **Silence is not consent** — `verified_ops/rollout.py`. An unreachable rollout target is
  `UNREACHABLE`, never "probably fine".
- **mtime is evidence, not proof** — `verified_ops/wrap.py` compares (mtime, size) around the
  run, so a third process writing the artifact mid-run would still read as work landed, and a
  job rewriting byte-identical content on a coarse filesystem can read as a no-op. Where that
  matters, point `--artifact` at a file only this job writes.
- **A directory has an mtime too** — `verified_ops/freshness.py`. Point `path` at a folder by
  accident and a naive check calls it fresh forever; here it is `UNREADABLE`.
- **A config that checks nothing exits 0 by default** — `verified_ops/cli.py`. Every monitoring
  tool has this hole; here an empty or misspelled config is a `4`. Found by an external reviewer
  on day one, which is also why the mutants exist.

## Wiring it in

```bash
# cron: once a day, 09:10
10 9 * * *  cd /srv/app && /usr/bin/python3 -m verified_ops freshness --config verified-ops.json

# wrap an existing job in place -- no changes to the job itself
0 3 * * *   cd /srv/app && /usr/bin/python3 -m verified_ops wrap --artifact out/export.json -- ./nightly.sh
```

GitHub Actions, launchd and Task Scheduler work the same way: they only need the exit
code, which is why the contract is the actual product here. `--json` gives a machine
report for dashboards; `--dry-run` checks and prints without touching the alert rail.

## Requirements

Python 3.8+, standard library only. No server, no database, no account. Tested on
3.9 and 3.12 locally; CI runs 3.9 / 3.11 / 3.13 on Ubuntu, macOS and Windows.

## The rule this repo lives by

*A check with no mutant that makes it fail measures nothing.* Every state in `selftest.py`
is produced by planting the actual failure — a backdated file, an empty rewrite, a verify
that only exits 0, a job that no-ops, a checker that crashes — and demanding the right state
**and** the right exit code. `python3 selftest.py` prints `44 checks, 0 failed` and exits 0.
If you add a check, add its mutant.

## Roadmap

**Now — [v0.1.0](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter/releases/tag/v0.1.0).**
The three checks (`freshness`, `wrap`, `rollout`), one exit-code contract, 44 self-test checks
each with the mutant that breaks it, CI on three OSes × three Pythons.

**Next**, in the order we would take them:

- **A fourth check: parity across boxes over time.** `rollout` answers "is the fix on every box
  right now"; it cannot yet answer "which box has been silently drifting for a week".
- **Read-back adapters beyond the shell** — today a rollout target proves itself with a command.
  HTTP endpoints and SQL rows are the two we hit most often in our own fleet.
- **A one-file report a human can read**, so the evidence lands somewhere other than an exit code.
- **What we are deliberately not building:** a server, a daemon, a dashboard or an account. This
  kit sits next to heartbeat monitoring (healthchecks.io, cronitor, dead-man switches), which
  answers *did it fire?* — a genuinely different question from *did the work land?*

Every noticeable change ships as a new release, so the
[release feed](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter/releases) is the
record of what this kit can actually prove — which is the only claim it makes.

## Provenance

Distilled and sanitized from a live multi-machine agent fleet where all of these
failures happened to us first: a nightly artifact cold for two weeks behind a green
heartbeat, a checker crashing every night while the board showed a routine finding, a
keyboard fix that sat undelivered on one box for twelve days after being "rolled out".
Method, not data — none of the fleet's paths, hosts or secrets are here.

Neighbours from the same lab: [claude-bible](https://github.com/Palo-Alto-AI-Research-Lab/claude-bible)
(rules-as-files governance), [claude-consensus](https://github.com/Palo-Alto-AI-Research-Lab/claude-consensus)
(cross-machine agreement), [agent-runtime-integrity-bench](https://github.com/Palo-Alto-AI-Research-Lab/agent-runtime-integrity-bench)
(integrity scenarios against real agent SDKs — that one tests *someone else's* runtime,
this one instruments *your own* jobs),
[verbatim-citation-gate](https://github.com/Palo-Alto-AI-Research-Lab/verbatim-citation-gate)
(catch fabricated RAG citations).

Contributions welcome — see [AGENTS.md](AGENTS.md) for how this repo expects changes to
be proven, whether a human or an agent is writing them.

MIT. Use it, fork it, no attribution needed.

---

<!--ecosystem-map:start-->

## 🧩 One piece of a working system

This repository is one piece lifted out of a live operation: one non-technical founder, an AI
cofounder, and a fleet of machines that reach consensus with each other and wake the human only
for money or the irreversible. It was extracted after it survived production, not written as a
demo — and it runs on its own: nothing here phones home to the rest.

**See how the whole thing fits together → [SYSTEM.md](https://github.com/tonydzi/tonydzi/blob/main/SYSTEM.md)**

Its closest neighbours in the **gates** layer: [`break-it-first`](https://github.com/tonydzi/break-it-first) · [`verbatim-citation-gate`](https://github.com/tonydzi/verbatim-citation-gate) · [`verdict-contract`](https://github.com/tonydzi/verdict-contract)

<!--ecosystem-map:end-->

## AI contributors

This project is built by a human + AI team, and the git log says so: Claude writes most of
the code, Codex and Grok review it, Gemini feeds the research. Each is credited on a commit
**only if its output changed that commit's content** — no decorative credits. Lab-wide
policy, one source for every repo: [AI-CONTRIBUTORS.md](https://github.com/Palo-Alto-AI-Research-Lab/.github/blob/main/AI-CONTRIBUTORS.md).
