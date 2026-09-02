"""Shared sampling engine.

Both the non-interactive snapshot (`fm --once`) and the Textual TUI use this.
It holds the stateful samplers (CPU-time delta, page-I/O delta) and assembles
one full dashboard snapshot.
"""
from __future__ import annotations

from datetime import datetime

from .smc import read_fan, read_temps
from .procs import ProcSampler
from .memory import MemorySampler, load_avg, ncpu, uptime_s
from .regime import verdict, recommend, system_advisories
from .watchdog import load as load_watchdog


class Engine:
    """Holds the samplers and assembles one dashboard snapshot."""

    def __init__(self):
        self.procs_sampler = ProcSampler()
        self.mem_sampler = MemorySampler()
        self.cores = ncpu()
        self._frame = 0
        self._temps = None

    def snapshot(self) -> dict:
        self._frame += 1
        procs = self.procs_sampler.sample()
        mem = self.mem_sampler.sample()
        fan = read_fan()
        # The full temp scan is the slowest read; do it every other frame.
        temps = read_temps() if self._frame % 2 == 1 else self._temps
        self._temps = temps
        l1, l5, l15 = load_avg()
        v = verdict(procs, mem, fan, temps, l1, self.cores)
        recs = recommend(procs, v)
        advisories = system_advisories(procs)
        wd = load_watchdog(days=1, max_events=8)
        up = uptime_s()
        header_sub = (
            f"{datetime.now():%H:%M:%S}  ·  up {fmt_uptime(up)}  ·  "
            f"{len(procs)} procs"
        )
        return {
            "fan": fan, "temps": temps, "mem": mem, "procs": procs,
            "load1": l1, "load5": l5, "load15": l15, "cores": self.cores,
            "verdict": v, "recs": recs, "advisories": advisories,
            "watchdog": wd, "header_sub": header_sub,
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
