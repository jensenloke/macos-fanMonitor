"""SMC access via the Stats.app read-only helper.

Fan RPM / target / range and temperature sensors are read from
/Applications/Stats.app/Contents/Resources/smc — the same binary the
watchdog uses, so no extra drivers or privileges are needed.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

SMC = "/Applications/Stats.app/Contents/Resources/smc"

# Sensors worth surfacing by name; everything else is collapsed.
NOTABLE = {
    "Tp0W": "CPU core (peak)",
    "Tp3P": "CPU complex",
    "TCMz": "CPU (TCMz)",
    "TCMb": "CPU (TCMb)",
    "TVD0": "GPU die",
    "TH0x": "SSD",
    "TaLW": "air outlet",
    "TaLR": "air inlet",
    "TfC0": "fan 0",
}

_TEMP_LINE = re.compile(r"^\[([A-Za-z0-9]+)\]\s+([0-9.]+)", re.MULTILINE)


@dataclass
class Fan:
    rpm: float = 0.0
    target: float = 0.0
    min_rpm: float = 0.0
    max_rpm: float = 6550.0
    mode: str = "?"
    # True: a fan was reported. False: the SMC answered "0 fans" (a fanless
    # MacBook Air). None: no SMC reader available, so we can't tell.
    present: bool | None = None

    @property
    def duty(self) -> float:
        """0..1 fraction of the fan's usable range."""
        if not self.present:
            return 0.0
        span = self.max_rpm - self.min_rpm
        if span <= 0:
            return 0.0
        return max(0.0, min(1.0, (self.rpm - self.min_rpm) / span))

    @property
    def fanless(self) -> bool:
        return self.present is False


@dataclass
class Temps:
    hottest_key: str = ""
    hottest_c: float = 0.0
    notable: dict = field(default_factory=dict)  # key -> (label, C)
    count: int = 0


def _run(*args, timeout=6.0) -> str:
    try:
        out = subprocess.run(
            [SMC, *args], capture_output=True, text=True, timeout=timeout
        )
        return out.stdout or ""
    except Exception:
        return ""


def read_fan() -> Fan:
    fan = Fan()
    # Demo / test hook: FANMON_FANLESS=1 makes a fan machine behave like an Air.
    if os.environ.get("FANMON_FANLESS"):
        fan.present = False
        return fan
    txt = _run("fans")
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("Number of fans"):
            fan.present = _num(s) > 0
        elif s.startswith("Actual speed"):
            fan.present = True
            fan.rpm = _num(s)
        elif s.startswith("Target speed"):
            fan.target = _num(s)
        elif s.startswith("Minimal speed"):
            fan.min_rpm = _num(s)
        elif s.startswith("Maximum speed"):
            fan.max_rpm = _num(s) or 6550.0
        elif s.startswith("Mode"):
            fan.mode = s.split(":", 1)[-1].strip()
    return fan


def read_temps() -> Temps:
    t = Temps()
    txt = _run("list", "-t", timeout=8.0)
    for m in _TEMP_LINE.finditer(txt):
        key, val = m.group(1), float(m.group(2))
        if val <= 0.0 or val > 130.0:
            continue  # dead sensor / implausible
        t.count += 1
        if val > t.hottest_c:
            t.hottest_c = val
            t.hottest_key = key
        if key in NOTABLE:
            t.notable[key] = (NOTABLE[key], val)
    return t


def _num(s: str) -> float:
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", s.split(":", 1)[-1])
    return float(m.group(1)) if m else 0.0
