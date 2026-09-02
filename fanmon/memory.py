"""Memory / swap / compressor / pressure via sysctl + vm_stat + memory_pressure."""
from __future__ import annotations

import re
import subprocess

PAGE = 16384  # bytes; vm_stat page size on Apple Silicon


def _sh(cmd: str, timeout=10.0) -> str:
    try:
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        ).stdout
    except Exception:
        return ""


class MemorySampler:
    def __init__(self):
        self._prev_io = None  # (pageins, pageouts)

    def sample(self) -> dict:
        swap_t, swap_u, swap_f = self._swap()
        vm = self._vmstat()
        free_pct = self._pressure_free()
        io_rate = self._io_rate(vm)
        occupied = vm.get("occupied", 0)
        stored = vm.get("stored", 0)
        return {
            "swap_total_gb": swap_t,
            "swap_used_gb": swap_u,
            "swap_free_gb": swap_f,
            "swap_used_pct": (swap_u / swap_t * 100.0) if swap_t else 0.0,
            "comp_stored_pages": stored,
            "comp_occupied_pages": occupied,
            "comp_ratio": (stored / occupied) if occupied else 0.0,
            "comp_stored_gb": stored * PAGE / 2**30,
            "comp_occupied_gb": occupied * PAGE / 2**30,
            "free_pages": vm.get("free", 0),
            "free_gb": vm.get("free", 0) * PAGE / 2**30,
            "wired_gb": vm.get("wired", 0) * PAGE / 2**30,
            "free_pct": free_pct,
            "pagein_rate": io_rate[0],
            "pageout_rate": io_rate[1],
        }

    def _swap(self):
        out = _sh("sysctl vm.swapusage")
        def grab(k):
            m = re.search(rf"{k}\s*=\s*([\d.]+)M", out)
            return float(m.group(1)) / 1024.0 if m else 0.0
        return grab("total"), grab("used"), grab("free")

    def _vmstat(self):
        out = _sh("vm_stat")
        def grab(name):
            m = re.search(rf"{re.escape(name)}:\s+(\d+)", out)
            return int(m.group(1)) if m else 0
        return {
            "free": grab("Pages free"),
            "wired": grab("Pages wired down"),
            "stored": grab("Pages stored in compressor"),
            "occupied": grab("Pages occupied by compressor"),
            "pageins": grab("Pageins"),
            "pageouts": grab("Pageouts"),
        }

    def _pressure_free(self):
        out = _sh("memory_pressure 2>/dev/null | tail -3")
        m = re.search(r"free percentage:\s*(\d+)", out)
        return int(m.group(1)) if m else None

    def _io_rate(self, vm):
        cur = (vm.get("pageins", 0), vm.get("pageouts", 0))
        rate = (0, 0)
        if self._prev_io is not None:
            rate = (
                max(0, cur[0] - self._prev_io[0]),
                max(0, cur[1] - self._prev_io[1]),
            )
        self._prev_io = cur
        return rate


def load_avg() -> tuple:
    out = _sh("sysctl -n vm.loadavg")
    m = re.findall(r"[\d.]+", out)
    if len(m) >= 3:
        return float(m[0]), float(m[1]), float(m[2])
    return 0.0, 0.0, 0.0


def ncpu() -> int:
    out = _sh("sysctl -n hw.ncpu").strip()
    try:
        return int(out)
    except ValueError:
        return 1


def uptime_s() -> float:
    out = _sh("sysctl -n kern.boottime")
    m = re.search(r"sec\s*=\s*(\d+)", out)
    if not m:
        return 0.0
    import time
    return max(0.0, time.time() - int(m.group(1)))
