#!/usr/bin/env python3
"""Self-test: every check in this kit must be broken by a mutant.

The rule this repo lives by: a check with no mutant that makes it fail measures
nothing. So each test below does not just assert the happy path -- it plants the
exact failure the check exists to catch (a backdated file, an empty rewrite, a
verify that only exits 0, a job that no-ops, a checker that crashes) and demands
the right state AND the right exit code.

Runs the real CLI as a subprocess, so the exit codes tested are the ones your
scheduler will see, not what the library returns in-process.

    python selftest.py        # 0 = all green, 1 = something failed
"""

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FAILS = []
TOTAL = [0]


def ck(name, ok, detail=""):
    TOTAL[0] += 1
    print(("OK   " if ok else "FAIL ") + name + (("  -- " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def cli(args, cwd=None):
    """Run the CLI, return (exit code, stdout+stderr)."""
    p = subprocess.run([PY, "-m", "verified_ops"] + args, cwd=cwd or HERE,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       env=dict(os.environ, PYTHONPATH=HERE))
    return p.returncode, p.stdout.decode("utf-8", "replace")


def write(path, body="payload\n", age_h=0.0):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    if age_h:
        old = time.time() - age_h * 3600
        os.utime(path, (old, old))
    return path


def cfg(tmp, obj):
    p = os.path.join(tmp, "verified-ops.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return p


# --------------------------------------------------------------- freshness ---
def test_freshness():
    with tempfile.TemporaryDirectory() as tmp:
        art = write(os.path.join(tmp, "export.json"), '{"rows": 3}\n')
        c = cfg(tmp, {"artifacts": [{"name": "export", "path": "export.json",
                                     "max_age_h": 26, "min_bytes": 1, "contains": '"rows"'}]})
        rc, out = cli(["freshness", "--config", c])
        ck("freshness: fresh artifact -> CLEAN(0)", rc == 0 and "FRESH" in out, "rc=%d" % rc)

        # MUTANT 1: same job, same exit 0, but the artifact stopped moving.
        os.utime(art, (time.time() - 40 * 3600,) * 2)
        rc, out = cli(["freshness", "--config", c])
        ck("freshness: stale artifact -> FOUND(1)", rc == 1 and "STALE" in out, "rc=%d" % rc)

        # MUTANT 2: the artifact is gone entirely.
        os.remove(art)
        rc, out = cli(["freshness", "--config", c])
        ck("freshness: missing artifact -> FOUND(1)", rc == 1 and "MISSING" in out, "rc=%d" % rc)

        # only_if_exists: absence is a declared non-event, not an alarm -- as long as
        # something else was actually measured (see test_nothing_measured).
        write(os.path.join(tmp, "export.json"), '{"rows": 1}\n')
        c2 = cfg(tmp, {"artifacts": [
            {"name": "export", "path": "export.json", "max_age_h": 26},
            {"name": "opt", "path": "nope.json", "max_age_h": 1, "only_if_exists": True}]})
        rc, out = cli(["freshness", "--config", c2])
        ck("freshness: only_if_exists -> SKIPPED, CLEAN(0)",
           rc == 0 and "SKIPPED" in out and "FRESH" in out, "rc=%d" % rc)

        # MUTANT 3: fresh, but the job wrote an empty file (a very common quiet failure).
        write(os.path.join(tmp, "export.json"), "")
        c3 = cfg(tmp, {"artifacts": [{"name": "export", "path": "export.json",
                                      "max_age_h": 26, "min_bytes": 1}]})
        rc, out = cli(["freshness", "--config", c3])
        ck("freshness: fresh but empty -> FOUND(1)", rc == 1 and "EMPTY" in out, "rc=%d" % rc)

        # MUTANT 4: fresh, non-empty, but the body marker is gone (200-with-wrong-body class).
        write(os.path.join(tmp, "export.json"), "an error page, served with a smile\n")
        c4 = cfg(tmp, {"artifacts": [{"name": "export", "path": "export.json",
                                      "max_age_h": 26, "contains": '"rows"'}]})
        rc, out = cli(["freshness", "--config", c4])
        ck("freshness: marker missing -> FOUND(1)", rc == 1 and "NO_MARKER" in out, "rc=%d" % rc)


def test_nothing_measured():
    """MUTANT 14 (Codex T3 #1): a config that measures nothing must never report CLEAN."""
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = cli(["freshness", "--config", cfg(tmp, {"artifacts": []})])
        ck("freshness: no artifacts declared -> CRASHED(4)", rc == 4, "rc=%d" % rc)
        # typo in the key: the config parses, declares nothing, and used to exit 0
        rc, out = cli(["freshness", "--config", cfg(tmp, {"artefacts": [{"name": "x"}]})])
        ck("freshness: misspelled key -> CRASHED(4), never 0", rc == 4, "rc=%d" % rc)
        # everything optional and absent = nothing measured, however cheerful the config looks
        rc, out = cli(["freshness", "--config", cfg(tmp, {"artifacts": [
            {"name": "opt", "path": "nope.json", "max_age_h": 1, "only_if_exists": True}]})])
        ck("freshness: all rows skipped -> CRASHED(4)", rc == 4, "rc=%d" % rc)


def test_freshness_glob_decoy():
    with tempfile.TemporaryDirectory() as tmp:
        os.mkdir(os.path.join(tmp, "out"))
        write(os.path.join(tmp, "out", "dump-2020-01-01.json"), "old\n", age_h=100)
        write(os.path.join(tmp, "out", "dump-2020-01-02.json"), "new\n")
        c = cfg(tmp, {"artifacts": [{"name": "dumps", "newest_glob": "out/dump-*.json",
                                     "max_age_h": 26}]})
        rc, out = cli(["freshness", "--config", c])
        ck("freshness: newest_glob measures the newest match", rc == 0 and "matched 2" in out,
           "rc=%d out=%s" % (rc, out.strip()[:80]))
        # MUTANT 5: a wide mask lets a decoy hide a stall -- the tool must NAME the file it read.
        ck("freshness: names the file it measured", "dump-2020-01-02.json" in out)


def test_alert_rail():
    with tempfile.TemporaryDirectory() as tmp:
        write(os.path.join(tmp, "export.json"), "x\n", age_h=99)
        sentinel = os.path.join(tmp, "delivered.txt")
        good = [PY, "-c", "import sys;open(%r,'w').write('sent')" % sentinel]
        c = cfg(tmp, {"artifacts": [{"name": "e", "path": "export.json", "max_age_h": 1}],
                      "alert": {"command": good}})
        rc, _ = cli(["freshness", "--config", c])
        ck("alert: delivered -> FOUND(1)", rc == 1 and os.path.exists(sentinel), "rc=%d" % rc)

        # MUTANT 6: the alert rail is dead. A found problem that nobody heard is NOT a 1.
        os.remove(sentinel)
        bad = [PY, "-c", "import sys;sys.exit(7)"]
        c = cfg(tmp, {"artifacts": [{"name": "e", "path": "export.json", "max_age_h": 1}],
                      "alert": {"command": bad}})
        rc, out = cli(["freshness", "--config", c])
        ck("alert: undeliverable -> UNDELIVERED(3), not 1", rc == 3, "rc=%d" % rc)
        ck("alert: undelivered finding still printed", "STALE" in out)

        # --dry-run must never touch the rail.
        c = cfg(tmp, {"artifacts": [{"name": "e", "path": "export.json", "max_age_h": 1}],
                      "alert": {"command": good}})
        rc, out = cli(["freshness", "--config", c, "--dry-run"])
        ck("alert: --dry-run delivers nothing -> UNDELIVERED(3)",
           rc == 3 and not os.path.exists(sentinel), "rc=%d" % rc)


# ----------------------------------------------------------------- rollout ---
def test_rollout():
    with tempfile.TemporaryDirectory() as tmp:
        conf = write(os.path.join(tmp, "app.conf"), "ttl=900\n")
        base = {"rollout": {"fix": "ttl raised to 900", "targets": []}}

        base["rollout"]["targets"] = [{"name": "hub", "verify": [PY, "-c",
                                       "print(open(%r).read())" % conf], "expect": "ttl=900"}]
        rc, out = cli(["rollout", "--config", cfg(tmp, base)])
        ck("rollout: fact read back -> CLEAN(0)", rc == 0 and "APPLIED" in out, "rc=%d" % rc)

        # MUTANT 7: the box was reached, the fix is simply not there.
        write(conf, "ttl=60\n")
        rc, out = cli(["rollout", "--config", cfg(tmp, base)])
        ck("rollout: fact absent -> FOUND(1)", rc == 1 and "MISSING" in out, "rc=%d" % rc)

        # MUTANT 8: the box does not answer. Silence must never read as applied.
        base["rollout"]["targets"] = [{"name": "offline", "verify": [PY, "-c", "import sys;sys.exit(9)"],
                                       "expect": "ttl=900"}]
        rc, out = cli(["rollout", "--config", cfg(tmp, base)])
        ck("rollout: unreachable -> FOUND(1)", rc == 1 and "UNREACHABLE" in out, "rc=%d" % rc)

        # MUTANT 9: the whole point -- a verify that only exits 0 proves nothing.
        base["rollout"]["targets"] = [{"name": "lazy", "verify": [PY, "-c", "pass"]}]
        rc, out = cli(["rollout", "--config", cfg(tmp, base)])
        ck("rollout: exit-0-only verify -> WEAK, FOUND(1)", rc == 1 and "WEAK" in out, "rc=%d" % rc)

        # ${PYTHON} keeps portable examples off the python/python3/py guessing game.
        base["rollout"]["targets"] = [{"name": "portable", "verify": ["${PYTHON}", "-c",
                                       "print('ttl=900')"], "expect": "ttl=900"}]
        rc, out = cli(["rollout", "--config", cfg(tmp, base)])
        ck("rollout: ${PYTHON} expands to this interpreter", rc == 0 and "APPLIED" in out,
           "rc=%d" % rc)

        # An explicit opt-out is an answer, so it does not hold the rollout open -- as long
        # as at least one target actually proved something.
        base["rollout"]["targets"] = [
            {"name": "hub", "verify": ["${PYTHON}", "-c", "print('ttl=900')"], "expect": "ttl=900"},
            {"name": "cloud", "not_for_me": "no local config"}]
        rc, out = cli(["rollout", "--config", cfg(tmp, base)])
        ck("rollout: not_for_me beside a proof -> CLEAN(0)",
           rc == 0 and "NOT_FOR_ME" in out and "APPLIED" in out, "rc=%d" % rc)

        # MUTANT 12 (Codex T3 #1): every target opted out -> nothing was proven. Not green.
        base["rollout"]["targets"] = [{"name": "cloud", "not_for_me": "no local config"}]
        rc, out = cli(["rollout", "--config", cfg(tmp, base)])
        ck("rollout: only opt-outs -> CRASHED(4), never 0", rc == 4, "rc=%d" % rc)

        # MUTANT 13: an empty target list is a config that checks nothing.
        rc, out = cli(["rollout", "--config", cfg(tmp, {"rollout": {"fix": "x", "targets": []}})])
        ck("rollout: no targets -> CRASHED(4)", rc == 4, "rc=%d" % rc)


# -------------------------------------------------------------------- wrap ---
def test_wrap():
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "out.json")
        job_ok = [PY, "-c", "open(%r,'w').write('work')" % art]
        rc, out = cli(["wrap", "--artifact", art, "--config", os.path.join(tmp, "none.json"),
                       "--"] + job_ok)
        ck("wrap: job wrote the artifact -> CLEAN(0)", rc == 0 and "work landed" in out,
           "rc=%d" % rc)

        # MUTANT 10: the flagship case. Exit 0, nothing produced, nobody would ever notice.
        job_noop = [PY, "-c", "pass"]
        rc, out = cli(["wrap", "--artifact", art, "--config", os.path.join(tmp, "none.json"),
                       "--"] + job_noop)
        ck("wrap: exit 0 with no work -> FOUND(1)", rc == 1 and "silent no-op" in out,
           "rc=%d" % rc)

        # MUTANT 15 (Codex T3 #2): a wrapped job dying with Python's default exit 1 must NOT
        # land on the code that means "found a problem and announced it".
        job_dead = [PY, "-c", "raise RuntimeError('boom')"]
        rc, out = cli(["wrap", "--artifact", art, "--config", os.path.join(tmp, "none.json"),
                       "--"] + job_dead)
        ck("wrap: child crash (exit 1) -> CRASHED(4), never FOUND(1)", rc == 4, "rc=%d" % rc)

        # ...unless the code is declared a designed finding, and then it passes through.
        rc, out = cli(["wrap", "--artifact", art, "--config", os.path.join(tmp, "none.json"),
                       "--signal", "1,3", "--"] + job_dead)
        ck("wrap: --signal 1 passes the declared code through", rc == 1, "rc=%d" % rc)

        job_loud = [PY, "-c", "import sys;sys.exit(2)"]
        rc, out = cli(["wrap", "--artifact", art, "--config", os.path.join(tmp, "none.json"),
                       "--"] + job_loud)
        ck("wrap: undeclared non-zero -> CRASHED(4)", rc == 4, "rc=%d" % rc)


# ---------------------------------------------------------------- contract ---
def test_contract():
    prog = (
        "import sys; sys.path.insert(0, %r); from verified_ops import contract, guard\n" % HERE
    )
    cases = [
        ("crash -> CRASHED(4)", "def f():\n raise RuntimeError('boom')\nsys.exit(guard(f))", 4),
        ("finding -> FOUND(1)", "def f():\n return 1\nsys.exit(guard(f))", 1),
        ("clean -> CLEAN(0)", "def f():\n return None\nsys.exit(guard(f))", 0),
        ("explicit SystemExit survives", "def f():\n sys.exit(3)\nsys.exit(guard(f))", 3),
        ("KeyboardInterrupt -> CRASHED(4)",
         "def f():\n raise KeyboardInterrupt()\nsys.exit(guard(f))", 4),
        ("MemoryError -> CRASHED(4)", "def f():\n raise MemoryError()\nsys.exit(guard(f))", 4),
    ]
    for label, body, want in cases:
        p = subprocess.run([PY, "-c", prog + body], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        ck("contract: " + label, p.returncode == want, "rc=%d want=%d" % (p.returncode, want))


def test_cli_crashes_loudly():
    """MUTANT 11: break the checker itself. A dead checker must not look like a finding."""
    with tempfile.TemporaryDirectory() as tmp:
        broken = os.path.join(tmp, "verified-ops.json")
        with open(broken, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        rc, out = cli(["freshness", "--config", broken])
        ck("cli: broken config -> CRASHED(4), never 1", rc == 4, "rc=%d" % rc)
        ck("cli: crash says so on stderr", "crashed" in out.lower())


def test_examples_config_is_valid():
    ex = os.path.join(HERE, "examples", "verified-ops.json")
    with open(ex, "rb") as fh:
        obj = json.loads(fh.read().decode("utf-8"))
    ck("examples: config parses", isinstance(obj.get("artifacts"), list))
    ck("examples: every artifact declares max_age_h",
       all("max_age_h" in a for a in obj["artifacts"]))
    ck("examples: every rollout target declares expect or not_for_me",
       all(("expect" in t) or ("not_for_me" in t) for t in obj["rollout"]["targets"]))


def main():
    print("verified-ops selftest  (python %s)" % sys.version.split()[0])
    test_freshness()
    test_nothing_measured()
    test_freshness_glob_decoy()
    test_alert_rail()
    test_rollout()
    test_wrap()
    test_contract()
    test_cli_crashes_loudly()
    test_examples_config_is_valid()
    print("\n%d checks, %d failed" % (TOTAL[0], len(FAILS)))
    if FAILS:
        print("FAILED: " + ", ".join(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
