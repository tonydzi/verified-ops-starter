#!/usr/bin/env python3
"""A 20-line job that fails the way real jobs fail, so you can watch the kit catch it.

    python examples/demo_job.py --once      # writes out/export.json  (healthy)
    python examples/demo_job.py --no-op     # exits 0 and writes nothing (the quiet failure)
    python examples/demo_job.py --empty     # writes an empty file (the other quiet failure)
    python examples/demo_job.py --crash     # raises, under the guard -> exit 4

Nothing here is special: --no-op is exactly what a real job does when an API
returns an empty page, a filter matches nothing, or a token silently expires.
It exits 0 every time.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from verified_ops import guard  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "mode.txt"), "w", encoding="utf-8") as fh:
        fh.write("mode=verified\n")

    if "--crash" in sys.argv:
        raise RuntimeError("the job died -- and this is what a real crash looks like")
    if "--no-op" in sys.argv:
        print("done (fetched 0 rows)")   # the whole lie, in one honest-looking line
        return 0
    rows = [] if "--empty" in sys.argv else [{"id": 1}, {"id": 2}]
    body = "" if "--empty" in sys.argv else json.dumps({"rows": rows}, indent=2)
    with open(os.path.join(OUT, "export.json"), "w", encoding="utf-8") as fh:
        fh.write(body)
    print("done (%d rows)" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(guard(main))
