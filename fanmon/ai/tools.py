"""Read-only tools the agent may call, plus their OpenAI JSON schemas.

Every tool returns a JSON-serialisable dict; every failure becomes
{"error": ...} so a bad call never breaks the loop. Nothing here can mutate
the system — `ps`/`lsof`/`pmset`/`log show` are all reads.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from .context import build_packet


@dataclass
class ToolContext:
    engine: object
    snap: dict


def _sh(args: list, timeout: float) -> str:
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=timeout).stdout


def _find(ctx: ToolContext, pid: int):
    for p in ctx.snap["procs"]:
        if p.pid == pid:
            return p
    return None


def _proc_detail(ctx: ToolContext, pid: int) -> dict:
    out = _sh(["ps", "-p", str(pid), "-o",
               "pid=,ppid=,pcpu=,pmem=,rss=,vsz=,etime=,state=,command="], 5)
    line = out.strip().splitlines()
    detail: dict = {"pid": pid}
    if line:
        parts = line[0].split(None, 8)
        if len(parts) >= 9:
            detail.update({
                "ppid": _int(parts[1]), "cpu_pct_ps": _float(parts[2]),
                "mem_pct": _float(parts[3]), "rss_mb": _float(parts[4]) / 1024,
                "etime": parts[6], "state": parts[7],
            })
            toks = parts[8].split()
            argv = " ".join([os.path.basename(toks[0])] + toks[1:4])
            detail["argv"] = argv[:120]
    try:
        detail["open_files"] = max(0, len(
            _sh(["lsof", "-p", str(int(pid))], 5).splitlines()) - 1)
    except Exception:
        detail["open_files"] = None
    p = _find(ctx, pid)
    if p:
        detail["comm"] = p.comm
        detail["category"] = p.category
        detail["closeable"] = p.closeable
        detail["cpu_pct_delta"] = round(p.cpu_pct, 1)
        detail["children"] = [c.pid for c in ctx.snap["procs"]
                              if c.ppid == pid]
    return detail


def _process_tree(ctx: ToolContext, pid: int) -> dict:
    by_pid = {p.pid: p for p in ctx.snap["procs"]}
    ancestors = []
    cur = by_pid.get(pid)
    seen = set()
    while cur and cur.ppid and cur.ppid not in seen and cur.ppid in by_pid:
        seen.add(cur.ppid)
        cur = by_pid[cur.ppid]
        ancestors.append({"pid": cur.pid, "comm": cur.comm})
    children = [{"pid": p.pid, "comm": p.comm}
                for p in ctx.snap["procs"] if p.ppid == pid]
    me = by_pid.get(pid)
    return {"pid": pid, "comm": me.comm if me else None,
            "ancestors": ancestors, "children": children}


def _resample(ctx: ToolContext) -> dict:
    ctx.snap = ctx.engine.snapshot()
    return build_packet(ctx.snap)


def _recent_logs(minutes: int, filter: str) -> dict:
    minutes = max(1, min(10, int(minutes)))
    f = (filter or "")[:40].replace("\\", "\\\\").replace('"', '\\"')
    pred = f'eventMessage CONTAINS[c] "{f}"'
    out = _sh(["log", "show", "--last", f"{minutes}m", "--style", "compact",
               "--predicate", pred], 15)
    lines = out.splitlines()
    return {"minutes": minutes, "filter": filter, "truncated": len(lines) > 60,
            "lines": lines[-60:]}


def _thermal_state() -> dict:
    return {
        "therm": _sh(["pmset", "-g", "therm"], 5)[:1500],
        "batt": _sh(["pmset", "-g", "batt"], 5)[:800],
    }


def _watchdog_events() -> dict:
    from ..watchdog import load
    wd = load(days=2, max_events=20)
    return {
        "probe_state": wd.probe_state,
        "events": [{"day": e.day, "time": e.time, "state": e.to_state,
                    "rpm": e.rpm, "detail": e.detail[:120]}
                   for e in wd.events],
    }


def _int(s):
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _float(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "proc_detail",
        "description": "Details for one PID: cpu/mem/rss, elapsed, state, truncated argv, open-file count, children, category, closeable.",
        "parameters": {"type": "object",
                       "properties": {"pid": {"type": "integer"}},
                       "required": ["pid"]}}},
    {"type": "function", "function": {
        "name": "process_tree",
        "description": "Ancestor chain and direct children (pid, comm) for a PID.",
        "parameters": {"type": "object",
                       "properties": {"pid": {"type": "integer"}},
                       "required": ["pid"]}}},
    {"type": "function", "function": {
        "name": "resample",
        "description": "Take a fresh system snapshot and return the full packet again.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "recent_logs",
        "description": "macOS unified log lines matching a message filter, last N minutes (max 10).",
        "parameters": {"type": "object",
                       "properties": {
                           "minutes": {"type": "integer"},
                           "filter": {"type": "string"}},
                       "required": ["minutes", "filter"]}}},
    {"type": "function", "function": {
        "name": "thermal_state",
        "description": "Raw `pmset -g therm` and `pmset -g batt` output.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "watchdog_events",
        "description": "Last 20 fan-activity events from the local watchdog logs.",
        "parameters": {"type": "object", "properties": {}}}},
]


def run_tool(ctx: ToolContext, name: str, args: dict) -> dict:
    """Dispatch one tool call; all failures become {"error": ...}."""
    try:
        if name == "proc_detail":
            return _proc_detail(ctx, int(args.get("pid", 0)))
        if name == "process_tree":
            return _process_tree(ctx, int(args.get("pid", 0)))
        if name == "resample":
            return _resample(ctx)
        if name == "recent_logs":
            return _recent_logs(args.get("minutes", 5), args.get("filter", ""))
        if name == "thermal_state":
            return _thermal_state()
        if name == "watchdog_events":
            return _watchdog_events()
        return {"error": f"unknown tool '{name}'"}
    except Exception as e:
        return {"error": str(e) or type(e).__name__}


def result_json(ctx: ToolContext, name: str, args: dict) -> str:
    try:
        return json.dumps(run_tool(ctx, name, args), default=str)[:8000]
    except Exception as e:
        return json.dumps({"error": str(e)})
