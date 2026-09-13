"""CLI entry point.

Default: launch the interactive Textual TUI (lazygit/yazi-style).
`--once`: print a single rich snapshot and exit (for scripts / quick look).
`fm ai …`: scriptable setup/verify for the opt-in AI harness.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

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


# --- fm ai … ----------------------------------------------------------------

def _probe_models(url: str):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return None
    if "data" in data:                      # /v1/models (OpenAI shape)
        return [m.get("id", "?") for m in data["data"]]
    return [m.get("name", "?") for m in data.get("models", [])]


def _show_cfg(console: Console, cfg, path: str) -> None:
    t = cfg.triggers
    console.print(f"path            {path}")
    console.print(f"enabled         {cfg.enabled}")
    console.print(f"provider        {cfg.provider}")
    console.print(f"base_url        {cfg.base_url}")
    console.print(f"model           {cfg.model}")
    console.print(f"key_source      {cfg.key_source}")
    console.print(f"max_tool_rounds {cfg.max_tool_rounds}")
    console.print(f"cooldown_s      {cfg.cooldown_s}")
    console.print(f"triggers        fan {t.fan_duty_pct}% · throttle "
                  f"{t.throttle_pct}% · mem {t.mem_used_pct}% · swap "
                  f"{t.swap_used_pct}% · high x{t.high_severity_samples}")


def _ai_cmd(args, console: Console) -> int:
    from .ai import config as ai_config

    if args.ai_cmd == "providers":
        provs = ai_config.omp_providers()
        if provs:
            for name, p in provs.items():
                console.print(f"omp:{name:12} {p['base_url']}"
                              f"  models: {', '.join(p['models'])}")
        else:
            console.print("no omp providers (~/.omp/agent/models.yml)")
        for name, url in (("ollama", "http://localhost:11434/api/tags"),
                          ("lmstudio", "http://localhost:1234/v1/models")):
            models = _probe_models(url)
            if models is None:
                console.print(f"{name:16} not reachable")
            else:
                console.print(f"{name:16} up  models: "
                              f"{', '.join(models[:8]) or '(none)'}")
        return 0

    if args.ai_cmd == "setup":
        path = ai_config.default_path()
        if os.path.exists(path) and not args.force:
            console.print(f"[red]{path} exists — pass --force to overwrite[/]")
            return 2
        cfg = ai_config.AiConfig()
        if args.from_omp:
            p = ai_config.omp_providers().get(args.from_omp)
            if p is None:
                console.print(f"[red]no omp provider '{args.from_omp}'[/]")
                return 2
            cfg.base_url = p["base_url"]
            cfg.model = p["models"][0] if p["models"] else ""
            cfg.key_source = f"omp:{args.from_omp}"
        for flag, attr in (("base_url", "base_url"), ("model", "model"),
                           ("key_source", "key_source")):
            v = getattr(args, flag)
            if v is not None:
                setattr(cfg, attr, v)
        trig = {"fan_duty_pct": args.fan_duty, "throttle_pct": args.throttle,
                "mem_used_pct": args.mem, "swap_used_pct": args.swap,
                "high_severity_samples": args.high_samples}
        for k, v in trig.items():
            if v is not None:
                setattr(cfg.triggers, k, v)
        if args.cooldown is not None:
            cfg.cooldown_s = args.cooldown
        if args.max_tool_rounds is not None:
            cfg.max_tool_rounds = args.max_tool_rounds
        cfg.enabled = True
        ai_config.save(cfg, path)
        console.print(f"wrote {path}")
        _show_cfg(console, cfg, path)
        return 0

    if args.ai_cmd == "status":
        path = ai_config.default_path()
        cfg = ai_config.load()
        if cfg is None:
            console.print(f"{path} — does not exist (AI off)")
            return 2
        _show_cfg(console, cfg, path)
        if cfg.key_source == "none":
            console.print("api key         none needed")
        else:
            try:
                ai_config.resolve_api_key(cfg.key_source)
                console.print("api key         resolves")
            except Exception as e:
                console.print(f"api key         MISSING: {e}")
        return 0 if cfg.configured else 2

    if args.ai_cmd in ("enable", "disable"):
        cfg = ai_config.load()
        if cfg is None:
            console.print("[red]no config — run `fm ai setup` first[/]")
            return 2
        cfg.enabled = args.ai_cmd == "enable"
        ai_config.save(cfg)
        console.print(f"AI harness {'enabled' if cfg.enabled else 'disabled'}"
                      f" ({ai_config.default_path()})")
        return 0

    if args.ai_cmd == "test":
        cfg = ai_config.load()
        if not (cfg and cfg.configured):
            console.print("[red]AI not configured — run `fm ai setup`[/]")
            return 2
        from .ai.provider import OpenAICompatProvider, ProviderError
        from .ai.tools import TOOL_SCHEMAS, ToolContext, run_tool
        provider = OpenAICompatProvider(cfg.base_url, cfg.model,
                                        cfg.key_source)
        t0 = time.monotonic()
        try:
            if not args.tools:
                provider.chat(
                    [{"role": "user",
                      "content": "Reply with the single word OK."}],
                    tools=[], max_tokens=20)
                console.print(f"OK · {cfg.model} · "
                              f"{time.monotonic() - t0:.1f}s")
                return 0
            schema = [t for t in TOOL_SCHEMAS
                      if t["function"]["name"] == "thermal_state"]
            messages = [{"role": "user",
                         "content": "Call the thermal_state tool."}]
            try:
                msg = provider.chat(
                    messages, schema, max_tokens=256,
                    tool_choice={"type": "function",
                                 "function": {"name": "thermal_state"}})
            except ProviderError:
                msg = provider.chat(messages, schema, max_tokens=256)
            calls = msg.get("tool_calls") or []
            if not calls:
                console.print("[red]model did not issue a tool call[/]")
                return 2
            call = calls[0]
            res = run_tool(ToolContext(engine=None, snap={}),
                           "thermal_state", {})
            messages.append({"role": "assistant",
                             "content": msg.get("content"),
                             "tool_calls": calls})
            messages.append({"role": "tool",
                             "tool_call_id": call.get("id", ""),
                             "content": json.dumps(res, default=str)[:4000]})
            provider.chat(messages, schema, max_tokens=64)
            console.print(f"OK · tools round-trip · {cfg.model} · "
                          f"{time.monotonic() - t0:.1f}s")
            return 0
        except ProviderError as e:
            console.print(f"[red]{e}[/]")
            return 2
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="fm",
        description="macOS fan / CPU / memory monitor — why is my Mac hot, and what to close. Built for the Agentic Builders Collective (agenticbuilders.sg).",
        epilog="AI harness: `fm ai setup` configures it, `fm ai status` / "
               "`fm ai test` verify it. See docs/ai.md.",
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
    sub = ap.add_subparsers(dest="cmd")
    ai = sub.add_parser("ai", help="AI harness: providers / setup / status / "
                                   "test / enable / disable")
    aisub = ai.add_subparsers(dest="ai_cmd", required=True)
    aisub.add_parser("providers",
                     help="list omp providers and local Ollama / LM Studio")
    sp = aisub.add_parser("setup", help="write ~/.config/macos-fanMonitor/"
                                        "config.toml")
    sp.add_argument("--base-url")
    sp.add_argument("--model")
    sp.add_argument("--key-source",
                    help="omp:<name> | env:<VAR> | none")
    sp.add_argument("--from-omp", metavar="NAME",
                    help="prefill base_url/model/key_source from models.yml")
    sp.add_argument("--fan-duty", type=int)
    sp.add_argument("--throttle", type=int)
    sp.add_argument("--mem", type=int)
    sp.add_argument("--swap", type=int)
    sp.add_argument("--high-samples", type=int)
    sp.add_argument("--cooldown", type=int)
    sp.add_argument("--max-tool-rounds", type=int)
    sp.add_argument("--force", action="store_true",
                    help="overwrite an existing config file")
    aisub.add_parser("status", help="show the parsed config and key state")
    tp = aisub.add_parser("test", help="one chat round-trip")
    tp.add_argument("--tools", action="store_true",
                    help="also verify a tool-call round-trip")
    aisub.add_parser("enable")
    aisub.add_parser("disable")
    args = ap.parse_args(argv)

    console = Console()
    if args.cmd == "ai":
        return _ai_cmd(args, console)
    if args.once:
        return _run_once(console, args.warmup, ai=args.ai or bool(args.ask),
                         ask=args.ask)

    # Interactive TUI. Imported lazily so --once doesn't require a TTY.
    from .app import run_app
    return run_app(args.interval, animate=not args.no_anim)


if __name__ == "__main__":
    sys.exit(main())
