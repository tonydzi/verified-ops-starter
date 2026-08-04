"""The exit-code contract every check in this kit speaks.

The whole kit exists because of one failure mode: a job that reports on itself.
`exit 0` and a heartbeat are self-reports, and a Python process that dies on an
unhandled exception exits with 1 -- the *same* code many checks use for "I found
a problem". A dashboard that treats 1 as "found something, that's fine" therefore
paints a dead checker green. That is the silent failure this contract removes.

    0  CLEAN       nothing wrong; evidence checked and fresh
    1  FOUND       a real problem was found AND the alert was delivered
    3  UNDELIVERED a real problem was found and the alert could NOT be delivered
    4  CRASHED     the checker itself died

Rules that make the codes mean something:
  * 1 is only ever returned after delivery succeeded. If the alert rail is dead,
    the answer is 3, never 1 -- otherwise "problem found" and "problem announced"
    become indistinguishable.
  * Any uncaught exception must become 4. `guard()` does that. Without it, a
    crashing checker returns 1 and hides inside your "known signal" allow-list.
  * Your scoreboard should treat 1 as YELLOW (open finding, already announced),
    3 and 4 as RED. Anything else is RED too.
"""

CLEAN = 0
FOUND = 1
UNDELIVERED = 3
CRASHED = 4

NAMES = {
    CLEAN: "CLEAN",
    FOUND: "FOUND",
    UNDELIVERED: "UNDELIVERED",
    CRASHED: "CRASHED",
}


def name(code):
    """Human name for an exit code ('?' for anything outside the contract)."""
    return NAMES.get(code, "?")


def guard(fn, *args, **kwargs):
    """Run `fn` and return its exit code, turning any crash into CRASHED (4).

    Use it as the *only* statement in your `__main__` block:

        if __name__ == "__main__":
            sys.exit(guard(main))

    `SystemExit` is passed through unchanged: a check that decided on its own
    code (0/1/3) keeps it. `KeyboardInterrupt` and `MemoryError` are crashes
    like any other -- that is why this catches `BaseException` and not
    `Exception`. The traceback still goes to stderr; the code is what changes.
    """
    import sys
    import traceback

    try:
        rc = fn(*args, **kwargs)
    except SystemExit:
        raise
    except BaseException:  # noqa: B036 -- deliberate: a dead checker must not look like a finding
        traceback.print_exc()
        sys.stderr.write("verified-ops: the check itself crashed -> exit %d (CRASHED)\n" % CRASHED)
        return CRASHED
    return CLEAN if rc is None else int(rc)
