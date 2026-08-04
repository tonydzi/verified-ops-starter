"""Run a job and catch the failure it will never report itself: exit 0 with no work done.

    verified-ops wrap --artifact out/export.json -- python tools/export.py

Records the artifact's mtime, runs the command, then looks again. If the job
exits 0 but the artifact did not move, that is a silent no-op -- the single most
common way a scheduled job stays green for weeks while producing nothing. The
job cannot detect this about itself, which is exactly why the wrapper does it.

Exit codes. The quiet case is the point: child exited 0, artifact did not move
-> FOUND (1), or UNDELIVERED (3) if the alert could not be sent.

A non-zero child is a loud failure and comes back as CRASHED (4) by default --
NOT passed through. Passing it through would be a trap this kit exists to close:
a job that dies with Python's default exit 1 would land on exactly the code that
means "found a problem and announced it". If some non-zero code of yours really
is a designed finding, declare it: `--signal 1,3`. Declared codes pass through
unchanged, everything else is red.
"""

import os
import subprocess
import sys
import time

from . import contract
from .alert import Alerter


def _stamp(path):
    """(mtime, size) or None -- the two cheap facts that prove a rewrite happened."""
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def run(argv, artifact, alert_spec=None, out=None, signal=(), timeout_s=None):
    out = out or sys.stdout
    signal = set(int(c) for c in signal)
    before = _stamp(artifact)
    started = time.time()
    try:
        rc = subprocess.call(list(argv), timeout=timeout_s) if timeout_s else \
            subprocess.call(list(argv))
    except subprocess.TimeoutExpired:
        # A hung child is the quietest failure of all: without this the wrapper waits
        # forever and the scheduler shows a job that never finished, not one that failed.
        took = time.time() - started
        out.write("child did not finish within %ss (killed at %.0fs)\n" % (timeout_s, took))
        out.flush()
        text = ("verified-ops wrap: the job hung past its %ss timeout\n  command: %s"
                % (timeout_s, " ".join(argv)))
        ok, _how = Alerter(alert_spec).deliver(text)
        return contract.FOUND if ok else contract.UNDELIVERED
    took = time.time() - started
    after = _stamp(artifact)

    out.write("child exited %d in %.1fs\n" % (rc, took))
    out.flush()
    if rc != 0:
        if rc in signal:
            # --signal means "this code is the CHILD's own found-and-delivered signal",
            # so the wrapper deliberately does not deliver anything on its behalf.
            out.write("exit %d is a declared signal of the job itself (it owns delivery) "
                      "-- passing it through\n" % rc)
            return rc
        out.write("loud failure -- reported as %d (CRASHED). If exit %d is a designed "
                  "finding of yours, declare it with --signal %d\n" % (contract.CRASHED, rc, rc))
        return contract.CRASHED

    if after is None:
        why = "the job exited 0 but %s does not exist" % artifact
    elif before is not None and after == before:
        why = ("the job exited 0 but %s did not change (mtime %s, %d bytes) -- silent no-op"
               % (artifact, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(after[0])), after[1]))
    else:
        out.write("artifact moved: %s (%d bytes) -- work landed\n" % (artifact, after[1]))
        return contract.CLEAN

    text = "verified-ops wrap: %s\n  command: %s" % (why, " ".join(argv))
    out.flush()
    ok, how = Alerter(alert_spec).deliver(text)
    if not ok:
        return contract.UNDELIVERED
    out.write("alert delivered via %s\n" % how)
    return contract.FOUND
