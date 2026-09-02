"""CLI entry point.

Default: launch the interactive Textual TUI (lazygit/yazi-style).
`--once`: print a single rich snapshot and exit (for scripts / quick look).
"""
from __future__ import annotations

import argparse
import sys
import time

from rich.console import Console

from .engine import Engine
from . import render


def _run_once(console: Console, warmup: float):
    eng = Engine()
    eng.snapshot()          # warm-up sample: primes CPU / memory deltas
    time.sleep(warmup)
    snap = eng.snapshot()   # real sample with a delta window
    console.print(render.build(snap))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="fm",
        description="macOS fan / CPU / memory monitor — why is my Mac hot, and what to close. Built for the Agentic Builders Collective (agenticbuilders.sg).",
    )
    ap.add_argument("--once", "--snapshot", dest="once", action="store_true",
                    help="print a single snapshot frame and exit")
    ap.add_argument("--interval", type=float, default=2.0,
                    help="live refresh seconds (default 2.0)")
    ap.add_argument("--warmup", type=float, default=1.5,
                    help="delta warm-up seconds for --once (default 1.5)")
    ap.add_argument("--no-anim", action="store_true",
                    help="skip the animated ABC boot screen")
    args = ap.parse_args(argv)

    console = Console()
    if args.once:
        _run_once(console, args.warmup)
        return 0

    # Interactive TUI. Imported lazily so --once doesn't require a TTY.
    from .app import run_app
    return run_app(args.interval, animate=not args.no_anim)


if __name__ == "__main__":
    sys.exit(main())
