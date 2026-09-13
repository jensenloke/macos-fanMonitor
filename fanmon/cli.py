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


def _run_once(console: Console, warmup: float, ai: bool = False,
              ask: str | None = None) -> int:
    eng = Engine()
    eng.snapshot()          # warm-up sample: primes CPU / memory deltas
    time.sleep(warmup)
    snap = eng.snapshot()   # real sample with a delta window
    console.print(render.build(snap))
    if not ai:
        return 0
    from .ai import config as ai_config
    cfg = ai_config.load()
    if not (cfg and cfg.configured):
        console.print("[red]AI not configured — run `fm`, press A to set up[/]")
        return 2
    from .ai.agent import Agent
    from .ai.context import build_packet
    from .ai.provider import OpenAICompatProvider
    from .ai.tools import ToolContext
    provider = OpenAICompatProvider(cfg.base_url, cfg.model, cfg.key_source)
    ctx = ToolContext(engine=eng, snap=snap)
    d = Agent(provider, cfg).diagnose(build_packet(snap), ctx, ask, [])
    console.print(render.ai_panel(d, cfg))
    return 0 if not d.error else 2


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
    ap.add_argument("--ai", action="store_true",
                    help="with --once: also consult the AI harness")
    ap.add_argument("--ask", metavar="QUESTION",
                    help="question for the AI consult (implies --ai with --once)")
    args = ap.parse_args(argv)

    console = Console()
    if args.once:
        return _run_once(console, args.warmup, ai=args.ai or bool(args.ask),
                         ask=args.ask)

    # Interactive TUI. Imported lazily so --once doesn't require a TTY.
    from .app import run_app
    return run_app(args.interval, animate=not args.no_anim)


if __name__ == "__main__":
    sys.exit(main())
