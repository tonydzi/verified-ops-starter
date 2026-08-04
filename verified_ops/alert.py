"""Alert delivery, with the honest part kept honest.

A check that finds a problem and cannot announce it is *worse* than a check that
finds nothing, because both look quiet. So delivery has its own exit code (3),
and this module is the only place that decides whether delivery happened.

Two rails, configured per check:
  console (default) -- write the alert to stderr. Always deliverable; use it
                       when a human or a scheduler log actually reads stderr.
  command           -- run an external command (your pager, bot, webhook curl,
                       `notify-send`, whatever). Delivered only if it exits 0.
                       The alert text arrives on stdin AND as the last argument,
                       so both styles of receiver work.
"""

import subprocess
import sys


class Alerter(object):
    def __init__(self, spec=None, timeout=30):
        """spec: None/{} -> console. {"command": [...]} -> external command."""
        self.spec = spec or {}
        self.timeout = timeout

    def deliver(self, text):
        """Return (ok, how). ok=False means the caller must exit UNDELIVERED."""
        cmd = self.spec.get("command")
        if not cmd:
            sys.stderr.write(text.rstrip("\n") + "\n")
            sys.stderr.flush()
            return True, "console"
        if isinstance(cmd, str):
            cmd = [cmd]
        argv = list(cmd) + [text]
        try:
            p = subprocess.run(
                argv,
                input=text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
            )
        except Exception as exc:  # command missing, not executable, timed out
            sys.stderr.write("verified-ops: alert command failed (%s)\n" % exc)
            sys.stderr.write(text.rstrip("\n") + "\n")  # never swallow the finding itself
            return False, "command:error"
        if p.returncode != 0:
            sys.stderr.write(
                "verified-ops: alert command exited %d\n%s\n"
                % (p.returncode, p.stderr.decode("utf-8", "replace").strip())
            )
            sys.stderr.write(text.rstrip("\n") + "\n")
            return False, "command:exit%d" % p.returncode
        return True, "command"
