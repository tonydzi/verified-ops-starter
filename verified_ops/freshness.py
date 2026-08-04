"""Check the AGE of a job's real output, not the fact that the job ran.

Heartbeat monitoring answers "did it fire?". This answers "did the work land?".
The two are orthogonal, and only the second one catches the common quiet
failures: the model refused, the API 429'd, a dependency vanished, the job
looped over an empty list, the disk filled. In all of those the process exits 0,
stamps its heartbeat, and rots.

Config (JSON, see examples/verified-ops.json):

    {"artifacts": [
       {"name": "nightly export",
        "path": "out/export.json",       # the file the job REWRITES every healthy run
        "max_age_h": 26,                 # cadence + grace, so one missed run is borderline
        "min_bytes": 1,                  # optional: an empty rewrite is a silent failure
        "contains": "\"rows\":",         # optional: a marker taken from the BODY, not the name
        "cure": "python tools/export.py --once, then read out/export.log",
        "only_if_exists": false}         # optional: true -> absence is not an alarm
    ]}

Instead of "path" you may give "newest_glob" for jobs that write a NEW dated file
each run. Two traps, both paid for in production:
  * make the mask NARROW. A wide mask lets an unrelated file that happens to land
    in the same folder mask a real stall. This tool always prints WHICH file it
    measured and how many matched, so a decoy is visible.
  * mtime over a synced folder (Syncthing, Dropbox, rsync) is not proof of work:
    the sync engine stamps a fresh mtime while copying an OLD file onto this box.
    Only point newest_glob at a directory your sync engine cannot touch.
"""

import glob as globmod
import json
import os
import time

from . import contract
from .alert import Alerter

FRESH = "FRESH"
STALE = "STALE"
MISSING = "MISSING"
EMPTY = "EMPTY"
NO_MARKER = "NO_MARKER"
UNREADABLE = "UNREADABLE"
SKIPPED = "SKIPPED"

_BAD = (STALE, MISSING, EMPTY, NO_MARKER, UNREADABLE)
_READ_CAP = 5 * 1024 * 1024  # never slurp a huge artifact just to look for a marker


def _resolve(spec, root):
    """Return (path_or_None, matched_count, note) for one artifact spec."""
    if spec.get("path"):
        p = spec["path"]
        p = p if os.path.isabs(p) else os.path.join(root, p)
        return (p if os.path.exists(p) else None), (1 if os.path.exists(p) else 0), ""
    pattern = spec.get("newest_glob")
    if not pattern:
        raise ValueError("artifact %r has neither 'path' nor 'newest_glob'" % spec.get("name"))
    pattern = pattern if os.path.isabs(pattern) else os.path.join(root, pattern)
    hits = [h for h in globmod.glob(pattern) if os.path.isfile(h)]
    if not hits:
        return None, 0, ""
    newest = max(hits, key=os.path.getmtime)
    note = "matched %d, measured %s" % (len(hits), os.path.basename(newest))
    return newest, len(hits), note


def check_one(spec, root=".", now=None):
    """Evaluate one artifact. Returns a dict -- never raises on a bad artifact,
    only on a malformed spec (that is a bug in your config, not a finding)."""
    now = time.time() if now is None else now
    name = spec.get("name") or spec.get("path") or spec.get("newest_glob") or "<unnamed>"
    max_age_h = float(spec["max_age_h"])
    out = {"name": name, "state": FRESH, "age_h": None, "detail": "", "cure": spec.get("cure", "")}

    path, _n, note = _resolve(spec, root)
    if path is None:
        out["state"] = SKIPPED if spec.get("only_if_exists") else MISSING
        out["detail"] = "no such file: %s" % (spec.get("path") or spec.get("newest_glob"))
        return out
    out["file"] = path
    if note:
        out["detail"] = note

    try:
        st = os.stat(path)
    except OSError as exc:
        out["state"] = UNREADABLE
        out["detail"] = str(exc)
        return out

    age_h = (now - st.st_mtime) / 3600.0
    out["age_h"] = round(age_h, 2)
    if age_h > max_age_h:
        out["state"] = STALE
        out["detail"] = ("%.1fh old, limit %.1fh" % (age_h, max_age_h)) + (
            " (%s)" % note if note else ""
        )
        return out

    min_bytes = spec.get("min_bytes")
    if min_bytes is not None and st.st_size < int(min_bytes):
        out["state"] = EMPTY
        out["detail"] = "fresh but %d bytes, expected >= %s" % (st.st_size, min_bytes)
        return out

    marker = spec.get("contains")
    if marker:
        try:
            with open(path, "rb") as fh:
                body = fh.read(_READ_CAP)
        except OSError as exc:
            out["state"] = UNREADABLE
            out["detail"] = str(exc)
            return out
        if marker.encode("utf-8") not in body:
            out["state"] = NO_MARKER
            out["detail"] = "fresh, non-empty, but %r is not in the body" % marker
            return out
    return out


def report(results):
    """Human-readable alert text for the artifacts that are not fresh."""
    lines = []
    for r in results:
        if r["state"] in _BAD:
            line = "  [%s] %s" % (r["state"], r["name"])
            if r["detail"]:
                line += " -- " + r["detail"]
            lines.append(line)
            if r["cure"]:
                lines.append("      cure: " + r["cure"])
    if not lines:
        return ""
    return "verified-ops freshness: %d artifact(s) not fresh\n%s" % (len(
        [r for r in results if r["state"] in _BAD]), "\n".join(lines))


def run(config, root=".", dry_run=False, as_json=False, out=None):
    """Check every artifact in `config`. Returns an exit code from the contract."""
    import sys

    out = out or sys.stdout
    results = [check_one(spec, root) for spec in config.get("artifacts", [])]
    bad = [r for r in results if r["state"] in _BAD]
    measured = [r for r in results if r["state"] != SKIPPED]

    if as_json:
        out.write(json.dumps({"results": results, "bad": len(bad)}, indent=2) + "\n")
    else:
        for r in results:
            age = "" if r["age_h"] is None else " %.1fh" % r["age_h"]
            out.write("%-11s %s%s%s\n" % (
                r["state"], r["name"], age, (" -- " + r["detail"]) if r["detail"] else ""))

    if not measured:
        # Zero evidence is not good news. An empty/misspelled "artifacts" key, or a config
        # where every row is only_if_exists and nothing exists, would otherwise report the
        # cheerful 0 that this whole kit exists to stop.
        sys.stderr.write("verified-ops freshness: nothing was measured (%d artifact(s) declared, "
                         "%d skipped) -> exit %d\n" % (len(results), len(results), contract.CRASHED))
        return contract.CRASHED
    if not bad:
        return contract.CLEAN
    text = report(results)
    if dry_run:
        # UNDELIVERED, not FOUND: 1 means "announced", and --dry-run announces nothing.
        out.write("\n--dry-run: alert NOT delivered. It would have said:\n" + text + "\n")
        return contract.UNDELIVERED
    out.flush()  # keep stdout and the stderr alert in the order a human reads them
    ok, how = Alerter(config.get("alert")).deliver(text)
    if not ok:
        return contract.UNDELIVERED
    out.write("alert delivered via %s\n" % how)
    return contract.FOUND
