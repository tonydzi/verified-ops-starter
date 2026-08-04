"""Command line for the kit. Zero dependencies, stdlib only.

    verified-ops freshness --config verified-ops.json [--dry-run] [--json]
    verified-ops rollout   --config verified-ops.json [--dry-run] [--json]
    verified-ops wrap      --artifact out/x.json -- python tools/job.py
    verified-ops codes
"""

import argparse
import json
import os
import sys

from . import contract, freshness, rollout, wrap


def _load(path):
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _cmd_freshness(args):
    cfg = _load(args.config)
    root = args.root or os.path.dirname(os.path.abspath(args.config))
    return freshness.run(cfg, root=root, dry_run=args.dry_run, as_json=args.json)


def _cmd_rollout(args):
    cfg = _load(args.config)
    return rollout.run(cfg, dry_run=args.dry_run, as_json=args.json)


def _cmd_wrap(args):
    if not args.command:
        sys.stderr.write("verified-ops wrap: nothing to run (put the command after --)\n")
        return contract.CRASHED
    alert = None
    if args.config and os.path.isfile(args.config):
        alert = _load(args.config).get("alert")
    signal = [int(c) for c in (args.signal or "").replace(",", " ").split()]
    return wrap.run(args.command, args.artifact, alert_spec=alert, signal=signal,
                    timeout_s=(float(args.timeout_s) if args.timeout_s else None))


def _cmd_codes(_args):
    print(__doc__.strip().splitlines()[0])
    for code in (contract.CLEAN, contract.FOUND, contract.UNDELIVERED, contract.CRASHED):
        print("  %d  %s" % (code, contract.name(code)))
    print("\nScoreboard rule: 1 = yellow (open finding, already announced); 3 and 4 = red.")
    return contract.CLEAN


def build_parser():
    p = argparse.ArgumentParser(prog="verified-ops", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    f = sub.add_parser("freshness", help="check the age of each job's real output")
    f.add_argument("--config", default="verified-ops.json")
    f.add_argument("--root", default=None, help="resolve relative paths against this dir")
    f.add_argument("--dry-run", action="store_true", help="check, print, deliver nothing")
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=_cmd_freshness)

    r = sub.add_parser("rollout", help="prove a fix is applied on every target")
    r.add_argument("--config", default="verified-ops.json")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=_cmd_rollout)

    w = sub.add_parser("wrap", help="run a job and catch 'exit 0 with no work done'")
    w.add_argument("--artifact", required=True, help="the file the job must rewrite")
    w.add_argument("--config", default="verified-ops.json", help="only read for its alert rail")
    w.add_argument("--signal", default="", help="child exit codes that are designed findings "
                                                "(e.g. --signal 1,3); everything else non-zero "
                                                "is reported as 4")
    w.add_argument("--timeout-s", dest="timeout_s", default=None,
                   help="kill the job after N seconds and alert (a hung job is a silent job)")
    w.add_argument("command", nargs=argparse.REMAINDER)
    w.set_defaults(func=_cmd_wrap)

    c = sub.add_parser("codes", help="print the exit-code contract")
    c.set_defaults(func=_cmd_codes)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        sys.stderr.write("\nverified-ops: no subcommand -> nothing was checked (exit %d)\n"
                         % contract.CRASHED)
        return contract.CRASHED
    if getattr(args, "command", None) and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args.func(args)


def entry():
    """Console entry point -- everything runs under the crash guard."""
    sys.exit(contract.guard(main))
