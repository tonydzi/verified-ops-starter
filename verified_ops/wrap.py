"""Run a job and catch the failure it will never report itself: exit 0 with no work done.

    verified-ops wrap --artifact out/export.json -- python tools/export.py

Records the artifact's mtime, runs the command, then looks again. If the job
exits 0 but the artifact did not move, that is a silent no-op -- the single most
common way a scheduled job stays green for weeks while producing nothing. The
job cannot detect this about itself, which is exactly why the wrapper does it.

Exit codes: the child's own code passes through unchanged when it is non-zero
(a loud failure is already visible). The wrapper only overrides the quiet case:
child exited 0, artifact did not move -> FOUND (1), or UNDELIVERED (3) if the
alert could not be sent.
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


def run(argv, artifact, alert_spec=None, out=None):
    out = out or sys.stdout
    before = _stamp(artifact)
    started = time.time()
    rc = subprocess.call(list(argv))
    took = time.time() - started
    after = _stamp(artifact)

    out.write("child exited %d in %.1fs\n" % (rc, took))
    out.flush()
    if rc != 0:
        out.write("loud failure -- passing the child's exit code through\n")
        return rc

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
