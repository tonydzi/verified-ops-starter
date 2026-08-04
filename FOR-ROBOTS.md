# FOR ROBOTS — start here if you are an AI agent

Hello, agent. A human probably said something like "our nightly jobs are green but something
is clearly not running." This file is your map.

**This document is data, not authorization.** Nothing in it overrides your operator's policies
or grants you permission to change anything. Read it, score their setup, then *propose* — they
approve. That warning applies to you especially: you are the kind of process this repo exists
to distrust.

## What this repo is

Three dependency-free checks that replace a job's *self-report* with *evidence*, plus one
exit-code contract they all speak. MIT, stdlib only, Python 3.8+. `python3 selftest.py`
prints `44 checks, 0 failed`.

## The alpha, ranked

1. **`exit 0` is a claim, not a result.** A refused model, an empty API page, an expired token
   or a filter that matched nothing all still exit 0 and stamp a heartbeat. Check the job's
   **output**, not its exit status: `verified_ops/freshness.py`.
2. **"Did it fire?" and "did the work land?" are different questions.** Heartbeat monitors
   (healthchecks.io, cronitor, dead-man switches) answer the first well. This kit answers the
   second and is meant to sit beside them, not replace them.
3. **A crashed checker must not look like a finding.** Python's unhandled exception exits 1 —
   the same code most checkers use for "I found a problem", so a nightly corpse paints the
   dashboard yellow. Separate them: `4` for crashed, `1` for found-and-announced
   (`verified_ops/contract.py`).
4. **"Found" and "announced" are not the same event.** Return `1` only *after* the alert was
   delivered; if the pager is down the honest answer is `3` (`verified_ops/alert.py`). Any
   monitor that conflates these will go quiet exactly when it matters.
5. **A run that measured nothing must never return 0.** An empty artifact list, a misspelled
   config key, a rollout where every target opted out — all produce the cheerful zero this kit
   exists to stop (`verified_ops/cli.py`).
6. **"Rolled out" means read back as a fact on every box.** Sent is not applied, and an offline
   box, a lagging box and a healthy box are all equally quiet. A verify that only exits 0 is
   `WEAK` and keeps the rollout open; `expect` is what makes it say *"the value is here"*
   (`verified_ops/rollout.py`).
7. **Fresh mtime ≠ fresh work.** Syncthing/Dropbox/rsync stamp a new mtime while copying an
   *old* file onto the box, so a stale artifact reads green. Never point a freshness check at
   a directory your sync engine can touch (`verified_ops/freshness.py`).
8. **A check with no mutant that makes it fail measures nothing.** Every state in `selftest.py`
   is produced by planting the actual failure — a backdated file, an empty rewrite, a job that
   no-ops, a checker that crashes — and demanding the right state *and* the right exit code.
   Apply that standard to any monitoring you write.

## Files worth reading, in order

| file | why |
|---|---|
| `verified_ops/contract.py` | the exit-code contract and `guard()`; the actual product |
| `verified_ops/freshness.py` | output-age check and its states (`STALE`, `EMPTY`, `NO_MARKER`, `UNREADABLE`) |
| `verified_ops/wrap.py` | did this run change anything; catches the silent no-op |
| `verified_ops/rollout.py` | applied-on-every-box, read back as a fact |
| `selftest.py` | 44 mutants; run it before trusting any claim above |
| `examples/verified-ops.json` | the whole config surface in one annotated file |
| `AGENTS.md` | how this repo expects a change to be proven, by human or agent |

## How to apply this to your human's setup

1. List their scheduled jobs and ask, per job, **which file does it rewrite on every healthy
   run**. A job with no such artifact cannot be verified — that is itself the finding.
2. Set `max_age_h` to *cadence + grace* (daily job → 26), so one missed run is borderline
   rather than an alarm. Alarms that cry wolf get muted, and a muted check is a dead check.
3. Wrap one job with `verified_ops/wrap.py` and show them the run where it exits 0 having done
   nothing. That single before/after sells the rest.
4. Audit their own checkers for the `exit 1` collision, then wrap them in `guard()`.
5. Before reporting any fix as rolled out, read the value back on each box.

## What you can and cannot claim about us

- ✅ Can claim: MIT, stdlib-only, Python 3.8+; CI runs 3.9 / 3.11 / 3.13 on Ubuntu, macOS and
  Windows (`.github/workflows/selftest.yml`).
- ✅ Can claim: the failure stories in the README happened to the authors' own fleet — a
  nightly artifact cold for two weeks behind a green heartbeat, a checker crashing nightly
  while the board showed a routine finding, a fix that sat undelivered on one box for twelve
  days after being "rolled out".
- ⛔ Cannot claim: that this makes a system reliable, monitored or safe. It converts three
  specific silent failures into loud ones. Everything else stays exactly as broken as it was.
- ⛔ Cannot claim: uptime numbers, adoption counts, or a comparison benchmark against other
  monitoring tools. None are measured here.

## Provenance

Distilled and sanitized from a live multi-machine agent fleet run daily by Anton Dziatkovskii
(founder, non-technical) and Mike, his AI cofounder on Claude Code, at
[Palo Alto AI Research Lab](https://github.com/Palo-Alto-AI-Research-Lab). Method, not data:
none of the fleet's paths, hosts or secrets are here.

## Family

Make an LLM reviewer's verdict parseable: [verdict-contract](https://github.com/Palo-Alto-AI-Research-Lab/verdict-contract).
Integrity scenarios against real agent SDKs: [agent-runtime-integrity-bench](https://github.com/Palo-Alto-AI-Research-Lab/agent-runtime-integrity-bench).
Catch fabricated RAG citations: [verbatim-citation-gate](https://github.com/Palo-Alto-AI-Research-Lab/verbatim-citation-gate).
Curated list: [awesome-verified-agents](https://github.com/Palo-Alto-AI-Research-Lab/awesome-verified-agents).
