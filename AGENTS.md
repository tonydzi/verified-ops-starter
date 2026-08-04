# AGENTS.md — how to change this repo (human or agent)

This file is the contract for anyone editing here, including coding agents. It is short
on purpose; the repo is small on purpose.

## What this repo is

Three checks (`freshness`, `wrap`, `rollout`) plus one exit-code contract. It is a
**starter kit**: people copy it into their own ops and edit it. That makes clarity and
honest failure modes worth more than features.

## Non-negotiables

1. **Stdlib only, Python 3.8+.** A dependency here would have to be installed on every
   box that runs a cron job. If you think you need one, you need a different repo.
2. **Every check needs a mutant.** Add a check → add a test in `selftest.py` that plants
   the exact failure it exists to catch and asserts both the state and the exit code. A
   test that only asserts the happy path measures nothing.
3. **The exit-code contract is fixed**: `0` clean, `1` found **and delivered**, `3` found
   but undeliverable, `4` the checker crashed. Never return 1 for something nobody heard.
   Never let an exception escape as 1 — that is what `contract.guard()` is for.
4. **Silence is not success.** An unreachable target, an unreadable file or a missing
   answer is a finding, never a pass.
5. **No fabricated numbers.** README examples are pasted from real runs. If you change
   output, re-run and re-paste. Where something is inferred rather than measured, say so
   in the same sentence.

## Definition of done for a change

```bash
python3 selftest.py         # must print "N checks, 0 failed"
```

- new behaviour is covered by a mutant test, not just an example;
- the docstring at the top of the touched module still describes what the module does
  (these docstrings are the documentation — there is no separate docs site);
- README updated if a user-visible flag, state or exit code changed;
- no absolute paths, machine names, hostnames or credentials anywhere, including tests
  and comments.

## Where things live

```
verified_ops/contract.py   exit codes + guard()          <- read this first
verified_ops/freshness.py  artifact age / size / marker
verified_ops/wrap.py       run a job, detect a silent no-op
verified_ops/rollout.py    per-target proof by reading a fact
verified_ops/alert.py      the only place that decides "delivered"
verified_ops/cli.py        argument parsing, nothing clever
selftest.py                the mutants
examples/                  a config and a job that fails on purpose
```

## Good first contributions

- a state this kit is blind to (permissions changed, artifact truncated mid-write);
- a receiver recipe for a common alert rail that survives the argv trap (Slack, ntfy,
  systemd, Telegram);
- a Windows Task Scheduler / launchd recipe with the exit-code mapping spelled out;
- porting the contract to another language — the ideas are 200 lines, not a framework.

Open an issue with the failure you saw first; a reproduction is worth more than a design
essay. Bug reports that name the artifact a human can inspect later are the best kind.
