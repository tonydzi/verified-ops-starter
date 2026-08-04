# verified-ops-starter

**Your scheduled job says `exit 0`. Prove it did the work.**

[![selftest](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter/actions/workflows/selftest.yml/badge.svg)](https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter/actions/workflows/selftest.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](#requirements)
[![deps: none](https://img.shields.io/badge/dependencies-none-lightgrey.svg)](#requirements)

Three small checks, no server, no dependencies. They replace a job's *self-report*
with *evidence*:

| check | question it answers | catches |
|---|---|---|
| `freshness` | is the job's real **output** young enough? | exit 0 while the artifact rots |
| `wrap` | did this run actually **change** anything? | exit 0 with no work done |
| `rollout` | is the fix **on every box**, read back as a fact? | "rolled out" that never landed |

Everything speaks one [exit-code contract](#exit-code-contract) in which a dead
checker cannot look like a clean result.

## Why

An agent, a cron job and a nightly script all report on themselves, and the report
is the first thing to break:

- the model refused, the API returned an empty page, the token expired, the filter
  matched nothing — the process still **exits 0** and stamps its heartbeat;
- a checker written in Python dies on an unhandled exception and **exits 1** — the
  same code many checkers use for "I found a problem", so the dashboard paints the
  corpse yellow and moves on;
- the fix "was rolled out" because it was *sent*, and an offline box, a lagging box
  and a healthy box are all equally quiet.

Heartbeat monitoring (healthchecks.io, cronitor, dead-man switches) answers *did it
fire?* — a genuinely different question, and worth having. This kit answers *did the
work land?* and is designed to sit next to them, not replace them.

## Quickstart (5 minutes, nothing to install)

```bash
git clone https://github.com/Palo-Alto-AI-Research-Lab/verified-ops-starter
cd verified-ops-starter
python3 selftest.py        # 39 checks, every one of them broken by a mutant first
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

Three rules give the codes teeth:

- **1 is only returned after delivery succeeded.** If your pager is down the answer is
  3, never 1 — otherwise "problem found" and "problem announced" become the same event.
  `--dry-run` returns 3 for the same reason: it announces nothing.
- **A run that measured nothing returns 4, never 0.** An empty artifact list, a misspelled
  `artifacts` key, a rollout where every target opted out — all of them used to produce
  the cheerful zero this kit exists to stop.
- **Any uncaught exception becomes 4.** Wrap your own checkers too, it is one line:

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

`rollout` refuses to count a target whose `verify` only exits 0 — it comes back `WEAK`
and keeps the rollout open. Exit 0 is the verify saying *"I ran"*; `expect` is what
makes it say *"the value is here"*.

## Traps this kit already paid for

Each one cost a real silent outage before it became a line of code or a test:

- **`exit 1` collides.** Python's unhandled-exception code is the same code checkers use
  for "found something". Hence `guard()` and the 4.
- **Fresh mtime ≠ fresh work over a synced folder.** Syncthing/Dropbox/rsync stamp a new
  mtime while copying an *old* file onto the box, so a stale artifact reads green. Only
  point `newest_glob` at a directory your sync engine cannot touch.
- **A wide glob mask hides a stall.** One unrelated file landing in the same folder masks
  a dead job forever. The tool always prints *which* file it measured and how many matched.
- **200 with the wrong body.** Fresh and non-empty is not the same as correct — that is
  what `contains` is for, and the marker must come from the body, never the filename.
- **Alert receivers that read argv as filenames** (`cat`, `curl -d @-`) fail on the extra
  argument and turn a finding into an exit 3. The alert text arrives on **stdin as well**;
  use it.
- **Silence is not consent.** An unreachable rollout target is `UNREACHABLE`, never
  "probably fine".
- **A config that checks nothing exits 0 by default.** Every monitoring tool has this hole;
  here an empty or misspelled config is a `4`. Found by an external reviewer on day one —
  which is also why the mutants exist.

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

*A check with no mutant that makes it fail measures nothing.* Every state in
`selftest.py` is produced by planting the actual failure — a backdated file, an empty
rewrite, a verify that only exits 0, a job that no-ops, a checker that crashes — and
demanding the right state **and** the right exit code. If you add a check, add its mutant.

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
