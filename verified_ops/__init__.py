"""verified-ops-starter -- three small checks that turn a job's self-report into evidence.

    freshness  the age of the job's real OUTPUT, not its heartbeat
    rollout    a fix counts as applied only when a machine reads the fact back
    wrap       catch the quiet failure: exit 0 with no work done

Stdlib only, Python 3.8+. The exit-code contract lives in verified_ops.contract.
"""

from .contract import CLEAN, CRASHED, FOUND, UNDELIVERED, guard  # noqa: F401

__version__ = "0.1.0"
__all__ = ["CLEAN", "FOUND", "UNDELIVERED", "CRASHED", "guard", "__version__"]
