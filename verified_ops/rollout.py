"""Prove a fix is applied on every target by reading a FACT on each one.

"Rolled out" is the most expensive lie in fleet ops, because three different
things get reported with the same sentence:

    delivered  -- the file/package reached the box
    applied    -- something on the box actually changed
    proven     -- a machine read the changed value back

Only the third one counts here. A target is APPLIED only if its verify command
exits 0 *and* prints an expected fact -- a value, a hash, a version, a marker
line. A verify that merely exits 0 is a report about intent, so this tool
refuses to count it: such a target comes back WEAK and keeps the rollout open.

Silence is the other trap. An offline box, a lagging box and a healthy box are
all quiet, so anything that does not answer is UNREACHABLE, never "probably
fine".

Config (JSON, see examples/verified-ops.json):

    {"rollout": {
       "fix": "cache TTL raised to 900s",
       "timeout_s": 30,
       "targets": [
         {"name": "hub",
          "verify": ["ssh", "hub", "grep -o 'ttl=[0-9]*' /etc/app.conf"],
          "expect": "ttl=900"},
         {"name": "laptop",
          "verify": ["cat", "/etc/app.conf"],
          "expect": "ttl=900",
          "not_for_me": "runs the cloud config, no local file"}   # explicit opt-out
       ]}}
"""

import os
import subprocess
import sys

from . import contract
from .alert import Alerter

APPLIED = "APPLIED"
MISSING = "MISSING"
UNREACHABLE = "UNREACHABLE"
WEAK = "WEAK"
NOT_FOR_ME = "NOT_FOR_ME"

_BAD = (MISSING, UNREACHABLE, WEAK)


def check_target(target, timeout=30):
    """Run one target's verify command and judge it. Never raises."""
    name = target.get("name") or "<unnamed>"
    out = {"name": name, "state": APPLIED, "detail": ""}

    if target.get("not_for_me"):
        out["state"] = NOT_FOR_ME
        out["detail"] = str(target["not_for_me"])
        return out

    expect = target.get("expect")
    if not expect:
        # Deliberate: exit 0 alone is the verify saying "I ran", not "the fact is here".
        out["state"] = WEAK
        out["detail"] = "no 'expect' declared -- exit 0 alone proves nothing"
        return out

    cmd = target.get("verify")
    if not cmd:
        out["state"] = WEAK
        out["detail"] = "no 'verify' command declared"
        return out
    if isinstance(cmd, str):
        cmd = [cmd]
    # ${PYTHON} -> the interpreter running this check, and $VARS -> the environment.
    # Without it every portable example has to guess between python / python3 / py.
    cmd = [os.path.expandvars(str(c).replace("${PYTHON}", sys.executable)) for c in cmd]

    try:
        p = subprocess.run(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=float(target.get("timeout_s", timeout)),
        )
    except Exception as exc:
        out["state"] = UNREACHABLE
        out["detail"] = "verify did not answer: %s" % exc
        return out

    body = p.stdout.decode("utf-8", "replace")
    if p.returncode != 0:
        out["state"] = UNREACHABLE
        out["detail"] = "verify exited %d: %s" % (p.returncode, body.strip()[:200])
        return out
    if expect not in body:
        out["state"] = MISSING
        out["detail"] = "fact %r not found in the verify output" % expect
        return out
    out["detail"] = "read %r" % expect
    return out


def report(fix, results):
    lines = []
    for r in results:
        if r["state"] in _BAD:
            lines.append("  [%s] %s -- %s" % (r["state"], r["name"], r["detail"]))
    if not lines:
        return ""
    return "verified-ops rollout: %r is NOT proven on %d target(s)\n%s" % (
        fix, len(lines), "\n".join(lines))


def run(config, dry_run=False, as_json=False, out=None):
    import json
    import sys

    out = out or sys.stdout
    spec = config.get("rollout") or {}
    fix = spec.get("fix", "<unnamed fix>")
    timeout = float(spec.get("timeout_s", 30))
    results = [check_target(t, timeout) for t in spec.get("targets", [])]
    bad = [r for r in results if r["state"] in _BAD]

    if as_json:
        out.write(json.dumps({"fix": fix, "results": results, "bad": len(bad)}, indent=2) + "\n")
    else:
        out.write("fix: %s\n" % fix)
        for r in results:
            out.write("%-12s %s -- %s\n" % (r["state"], r["name"], r["detail"]))

    if not bad:
        return contract.CLEAN
    text = report(fix, results)
    if dry_run:
        out.write("\n--dry-run: alert NOT delivered. It would have said:\n" + text + "\n")
        return contract.FOUND
    out.flush()
    ok, how = Alerter(config.get("alert")).deliver(text)
    if not ok:
        return contract.UNDELIVERED
    out.write("alert delivered via %s\n" % how)
    return contract.FOUND
