"""Per-core CPU utilisation via Mach `host_processor_info` (ctypes, no sudo).

`ps` gives per-process CPU; this gives what each *core* is doing, which is the
number a MacBook Air user actually feels (a pinned P-core is why the chassis
is warm). Deltas between two samples yield a real utilisation window.

Apple Silicon reports efficiency cores first, then performance cores; the
counts come from `hw.perflevel1.logicalcpu` (E) and `hw.perflevel0.logicalcpu`
(P). Intel Macs have a single level and are simply labelled `C`.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
from dataclasses import dataclass, field

_PROCESSOR_CPU_LOAD_INFO = 2
_CPU_STATE_USER, _CPU_STATE_SYSTEM, _CPU_STATE_IDLE, _CPU_STATE_NICE = 0, 1, 2, 3


@dataclass
class CpuStats:
    per_core: list[float] = field(default_factory=list)   # busy % per core
    labels: list[str] = field(default_factory=list)       # "P0", "E3", "C1"
    total_pct: float = 0.0        # average busy % across cores (0..100)
    user_pct: float = 0.0
    sys_pct: float = 0.0
    p_cores: int = 0
    e_cores: int = 0
    ncpu: int = 0
    available: bool = False       # False until two samples exist / on failure

    @property
    def p_busy(self) -> float:
        cores = [c for c, l in zip(self.per_core, self.labels) if l[0] == "P"]
        return sum(cores) / len(cores) if cores else 0.0

    @property
    def e_busy(self) -> float:
        cores = [c for c, l in zip(self.per_core, self.labels) if l[0] == "E"]
        return sum(cores) / len(cores) if cores else 0.0


def _sysctl_int(key: str) -> int:
    try:
        out = subprocess.run(["sysctl", "-n", key], capture_output=True,
                             text=True, timeout=3).stdout.strip()
        return int(out)
    except Exception:
        return 0


def perf_levels() -> tuple[int, int]:
    """(performance cores, efficiency cores); (0, 0) when not Apple Silicon."""
    return _sysctl_int("hw.perflevel0.logicalcpu"), _sysctl_int("hw.perflevel1.logicalcpu")


class _Mach:
    def __init__(self):
        self.ok = False
        try:
            self.libc = ctypes.CDLL(ctypes.util.find_library("c"))
            self.libc.mach_host_self.restype = ctypes.c_uint
            self.libc.mach_task_self.restype = ctypes.c_uint
            self.host = self.libc.mach_host_self()
            self.ok = True
        except Exception:
            self.libc = None

    def ticks(self) -> list[tuple[int, int, int, int]]:
        """[(user, system, idle, nice), …] per core, or [] on failure."""
        if not self.ok:
            return []
        count = ctypes.c_uint()
        info = ctypes.POINTER(ctypes.c_uint)()
        n = ctypes.c_uint()
        ret = self.libc.host_processor_info(
            self.host, _PROCESSOR_CPU_LOAD_INFO, ctypes.byref(count),
            ctypes.byref(info), ctypes.byref(n))
        if ret != 0 or not count.value:
            return []
        try:
            vals = [info[i] for i in range(n.value)]
        finally:
            self.libc.vm_deallocate(self.libc.mach_task_self(),
                                    ctypes.cast(info, ctypes.c_void_p),
                                    n.value * 4)
        return [tuple(vals[i * 4:i * 4 + 4]) for i in range(count.value)]


class CpuSampler:
    def __init__(self):
        self._mach = _Mach()
        self._prev: list[tuple[int, int, int, int]] | None = None
        self.p_cores, self.e_cores = perf_levels()

    def _labels(self, n: int) -> list[str]:
        if self.p_cores + self.e_cores == n and self.e_cores:
            return [f"E{i}" for i in range(self.e_cores)] + \
                   [f"P{i}" for i in range(self.p_cores)]
        return [f"C{i}" for i in range(n)]

    def sample(self) -> CpuStats:
        cur = self._mach.ticks()
        stats = CpuStats(p_cores=self.p_cores, e_cores=self.e_cores,
                         ncpu=len(cur))
        if not cur:
            return stats
        stats.labels = self._labels(len(cur))
        prev, self._prev = self._prev, cur
        if prev is None or len(prev) != len(cur):
            stats.per_core = [0.0] * len(cur)
            return stats

        busy_sum = user_sum = sys_sum = total_sum = 0.0
        for (u0, s0, i0, n0), (u1, s1, i1, n1) in zip(prev, cur):
            du, ds, di, dn = u1 - u0, s1 - s0, i1 - i0, n1 - n0
            tot = du + ds + di + dn
            if tot <= 0:
                stats.per_core.append(0.0)
                continue
            busy = (du + ds + dn) / tot * 100.0
            stats.per_core.append(busy)
            busy_sum += busy
            user_sum += du + dn
            sys_sum += ds
            total_sum += tot
        n = len(cur)
        stats.total_pct = busy_sum / n if n else 0.0
        if total_sum:
            stats.user_pct = user_sum / total_sum * 100.0
            stats.sys_pct = sys_sum / total_sum * 100.0
        stats.available = True
        return stats
