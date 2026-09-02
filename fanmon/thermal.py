"""Thermal-pressure state from `pmset -g therm` (read-only, no sudo).

On a fanless MacBook Air the equivalent of "the fan is spinning" is
"macOS is throttling the CPU". `pmset -g therm` reports that directly:

    CPU_Scheduler_Limit = 100     # % of scheduler time the CPU may use
    CPU_Available_CPUs  = 8
    CPU_Speed_Limit     = 100     # % of max clock allowed (100 = unthrottled)

When no throttling has ever been applied since boot, pmset prints only
"Note: … has been recorded" lines, which we treat as unthrottled.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass


@dataclass
class Thermal:
    speed_limit: int | None = None       # CPU_Speed_Limit, 100 = no throttle
    scheduler_limit: int | None = None   # CPU_Scheduler_Limit
    available_cpus: int | None = None    # CPU_Available_CPUs
    known: bool = False                  # pmset answered at all

    @property
    def throttle_pct(self) -> int:
        """How much clock macOS is holding back (0 = none)."""
        lim = 100 if self.speed_limit is None else self.speed_limit
        return max(0, 100 - lim)

    @property
    def throttled(self) -> bool:
        return self.throttle_pct > 0 or (
            self.scheduler_limit is not None and self.scheduler_limit < 100)


_KV = re.compile(r"^\s*(CPU_Speed_Limit|CPU_Scheduler_Limit|CPU_Available_CPUs)"
                 r"\s*=\s*(\d+)", re.MULTILINE)


def read_thermal() -> Thermal:
    t = Thermal()
    try:
        out = subprocess.run(["pmset", "-g", "therm"], capture_output=True,
                             text=True, timeout=4).stdout
    except Exception:
        return t
    if not out.strip():
        return t
    t.known = True
    for key, val in _KV.findall(out):
        v = int(val)
        if key == "CPU_Speed_Limit":
            t.speed_limit = v
        elif key == "CPU_Scheduler_Limit":
            t.scheduler_limit = v
        else:
            t.available_cpus = v
    # Demo / test hook: FANMON_THROTTLE=<speed limit %> forces a reading.
    forced = os.environ.get("FANMON_THROTTLE")
    if forced and forced.isdigit():
        t.speed_limit = max(0, min(100, int(forced)))
        t.known = True
    return t
