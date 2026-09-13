"""Snapshot -> JSON packet the agent sees.

PRIVACY: full command lines (Proc.command) are never included — only `comm`
and the classification category. Everything here is JSON-serialisable.
"""
from __future__ import annotations

from ..procs import CATEGORY_SYSTEM

_TOP = 12


def _proc_row(p) -> dict:
    return {
        "pid": p.pid, "comm": p.comm, "category": p.category,
        "closeable": p.closeable, "rss_mb": round(p.rss_mb, 1),
        "cpu_pct": round(p.cpu_pct, 1), "age_h": round(p.age_h, 2),
        "group": p.group,
    }


def _trend(hist: list, n: int = 60) -> dict:
    tail = hist[-n:]
    if not tail:
        return {}
    return {
        "first": round(tail[0], 1), "last": round(tail[-1], 1),
        "min": round(min(tail), 1), "max": round(max(tail), 1),
        "n": len(tail),
    }


def build_packet(snap: dict) -> dict:
    fan, temps, mem, cpu, therm = (snap["fan"], snap["temps"], snap["mem"],
                                   snap["cpu"], snap["thermal"])
    v = snap["verdict"]
    wd = snap["watchdog"]
    procs = snap["procs"]

    gauges = {
        "fanless": fan.fanless,
        "throttle_pct": therm.throttle_pct,
        "cpu_speed_pct": 100 - therm.throttle_pct,
        "mem_used_pct": round(mem["used_pct"], 1),
        "mem_used_gb": round(mem["used_gb"], 1),
        "swap_used_pct": round(mem["swap_used_pct"], 1),
        "swap_used_gb": round(mem["swap_used_gb"], 1),
        "compressor_ratio": round(mem["comp_ratio"], 2),
        "pagein_per_s": round(mem["pagein_rate"], 1),
        "pageout_per_s": round(mem["pageout_rate"], 1),
        "load1": snap["load1"], "load5": snap["load5"],
        "load15": snap["load15"], "cores": snap["cores"],
    }
    if not fan.fanless:
        gauges["fan_rpm"] = fan.rpm
        gauges["fan_duty_pct"] = round(fan.duty * 100, 1)
    if temps and temps.hottest_c:
        gauges["hottest_c"] = round(temps.hottest_c, 1)
        gauges["hottest_sensor"] = temps.hottest_key
    if cpu.available:
        gauges["cpu_total_pct"] = round(cpu.total_pct, 1)
        gauges["cpu_p_busy_pct"] = round(cpu.p_busy, 1)
        gauges["cpu_e_busy_pct"] = round(cpu.e_busy, 1)

    return {
        "machine": {
            "cores": snap["cores"], "ram_total_gb": round(mem["total_gb"], 1),
            "fanless": fan.fanless,
        },
        "gauges": gauges,
        "verdict": {
            "kind": v.kind, "headline": v.headline, "detail": v.detail,
            "severity": v.severity,
        },
        "deterministic_recommendations": [
            {"label": r.label, "category": r.category,
             "rss_mb": round(r.rss_mb, 1), "cpu_pct": round(r.cpu_pct, 1),
             "age_h": round(r.age_h, 2), "pids": r.pids, "reason": r.reason}
            for r in snap["recs"]
        ],
        "advisories": snap.get("advisories") or [],
        "watchdog": {
            "probe_state": wd.probe_state,
            "trigger_rpm": wd.trigger_rpm,
            "events": [{"day": e.day, "time": e.time, "state": e.to_state,
                        "rpm": e.rpm, "detail": e.detail[:100]}
                       for e in wd.events[:5]],
        },
        "trends": {
            "cpu": _trend(snap["cpu_hist"]),
            "mem": _trend(snap["mem_hist"]),
            "heat": _trend(snap["heat_hist"]),
        },
        "top_cpu": [_proc_row(p) for p in
                    sorted(procs, key=lambda p: p.cpu_pct, reverse=True)[:_TOP]],
        "top_rss": [_proc_row(p) for p in
                    sorted(procs, key=lambda p: p.rss_mb, reverse=True)[:_TOP]],
    }


def closeable_pids(snap: dict) -> set:
    return {p.pid for p in snap["procs"]
            if p.closeable and p.category != CATEGORY_SYSTEM}


def groups(snap: dict) -> dict:
    """group/rec label -> closeable member pids, for target expansion."""
    by_group: dict = {}
    for p in snap["procs"]:
        if p.closeable and p.category != CATEGORY_SYSTEM:
            by_group.setdefault(p.group, []).append(p.pid)
    out = {}
    for g, pids in by_group.items():
        out[g] = pids
        if len(pids) > 1:
            out[f"{g} x{len(pids)}"] = pids
    for r in snap["recs"]:
        out.setdefault(r.label, r.pids)
    return out
