"""Shared sampling engine.

Both the non-interactive snapshot (`fm --once`) and the Textual TUI use this.
It holds the stateful samplers (CPU-time delta, per-core ticks, page-I/O
delta) and assembles one full dashboard snapshot, plus short in-session
histories for the sparklines.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime

from .smc import read_fan, read_temps
from .cpu import CpuSampler
from .thermal import read_thermal
from .procs import ProcSampler
from .memory import MemorySampler, load_avg, ncpu, uptime_s
from .regime import verdict, recommend, system_advisories
from .watchdog import load as load_watchdog

HISTORY = 120   # samples kept for sparklines (~4 min at the 2 s default)


class Engine:
    """Holds the samplers and assembles one dashboard snapshot."""

    def __init__(self):
        self.procs_sampler = ProcSampler()
        self.mem_sampler = MemorySampler()
        self.cpu_sampler = CpuSampler()
        self.cores = ncpu()
        self._frame = 0
        self._temps = None
        self.cpu_hist: deque = deque(maxlen=HISTORY)    # total CPU busy %
        self.mem_hist: deque = deque(maxlen=HISTORY)    # RAM used %
        self.heat_hist: deque = deque(maxlen=HISTORY)   # fan duty % / throttle %

    def snapshot(self) -> dict:
        self._frame += 1
        procs = self.procs_sampler.sample()
        mem = self.mem_sampler.sample()
        cpu = self.cpu_sampler.sample()
        fan = read_fan()
        thermal = read_thermal()
        # The full temp scan is the slowest read; do it every other frame.
        temps = read_temps() if self._frame % 2 == 1 else self._temps
        self._temps = temps
        l1, l5, l15 = load_avg()
        v = verdict(procs, mem, fan, temps, l1, self.cores,
                    thermal=thermal, cpu=cpu)
        recs = recommend(procs, v)
        advisories = system_advisories(procs)
        wd = load_watchdog(days=1, max_events=8)
        up = uptime_s()

        if cpu.available:
            self.cpu_hist.append(cpu.total_pct)
        else:
            self.cpu_hist.append(
                min(100.0, sum(p.cpu_pct for p in procs) / (self.cores or 1)))
        self.mem_hist.append(mem["used_pct"])
        self.heat_hist.append(
            thermal.throttle_pct if fan.fanless else fan.duty * 100.0)

        header_sub = (
            f"{datetime.now():%H:%M:%S}  ·  up {fmt_uptime(up)}"
            f"  ·  {len(procs)} procs"
        )
        return {
            "fan": fan, "temps": temps, "mem": mem, "procs": procs,
            "cpu": cpu, "thermal": thermal, "fanless": fan.fanless,
            "load1": l1, "load5": l5, "load15": l15, "cores": self.cores,
            "verdict": v, "recs": recs, "advisories": advisories,
            "watchdog": wd, "header_sub": header_sub,
            "cpu_hist": list(self.cpu_hist), "mem_hist": list(self.mem_hist),
            "heat_hist": list(self.heat_hist),
        }


def fmt_uptime(s: float) -> str:
    d = int(s // 86400)
    h = int((s % 86400) // 3600)
    m = int((s % 3600) // 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"
