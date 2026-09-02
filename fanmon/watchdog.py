"""Read-only integration with dev.jensen.watchdog.

Parses fan-activity events and current probe status from the watchdog's
state files. Never writes to or modifies the watchdog.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

EVENTS_DIR = os.path.expanduser("~/watchdogs/state/events")
RUNNER_LOG = os.path.expanduser("~/watchdogs/state/runner.log")
CONFIG = os.path.expanduser("~/watchdogs/watchdogs.json")

_EVENT = re.compile(
    r"(?P<time>\d\d:\d\d)\s+fan-activity\s+(?P<from>\w+)\s*->\s*(?P<to>\w+):\s*(?P<rest>.*)"
)
_RPM = re.compile(r"fan\s+(\d+)\s+RPM")
_RECOVERED = re.compile(r"sensor recovered at (\d+) RPM")
_REARMED = re.compile(r"re-armed at (\d+) RPM")


@dataclass
class FanEvent:
    day: str
    time: str
    to_state: str
    rpm: int
    detail: str


@dataclass
class WatchdogInfo:
    loaded: bool = False
    trigger_rpm: int = 3000
    reset_rpm: int = 2700
    probe_state: str = "?"
    last_probe_line: str = ""
    events: list = field(default_factory=list)


def _config() -> dict:
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except Exception:
        return {}


def load(days: int = 1, max_events: int = 12) -> WatchdogInfo:
    info = WatchdogInfo()

    cfg = _config().get("fan_monitor", {})
    info.trigger_rpm = int(cfg.get("trigger_rpm", 3000))
    info.reset_rpm = int(cfg.get("reset_rpm", 2700))

    info.loaded = os.path.exists(RUNNER_LOG)

    # Current probe state from the tail of the runner log.
    info.probe_state, info.last_probe_line = _probe_state()

    # Fan events from today (and yesterday if today has none yet).
    info.events = _events(days, max_events)
    return info


def _probe_state() -> tuple:
    try:
        with open(RUNNER_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 200_000))
            tail = f.read().decode("utf-8", "ignore").splitlines()
    except Exception:
        return "?", ""
    for line in reversed(tail):
        if "fan-activity" in line:
            if "CRIT" in line:
                return "CRIT", line
            if "WARN" in line:
                return "WARN", line
            if "OK" in line:
                return "OK", line
    return "?", ""


def _events(days: int, max_events: int) -> list[FanEvent]:
    from datetime import date, timedelta
    events: list[FanEvent] = []
    today = date.today()
    files = []
    for i in range(days + 1):
        d = today - timedelta(days=i)
        p = os.path.join(EVENTS_DIR, f"{d.isoformat()}.log")
        if os.path.exists(p):
            files.append((d.isoformat(), p))
    for day, path in files:
        try:
            with open(path) as f:
                for line in f:
                    m = _EVENT.search(line)
                    if not m:
                        continue
                    rpm = 0
                    if r := _RPM.search(m.group("rest")):
                        rpm = int(r.group(1))
                    elif r := _RECOVERED.search(m.group("rest")):
                        rpm = int(r.group(1))
                    elif r := _REARMED.search(m.group("rest")):
                        rpm = int(r.group(1))
                    events.append(FanEvent(
                        day=day, time=m.group("time"),
                        to_state=m.group("to"), rpm=rpm,
                        detail=m.group("rest").strip(),
                    ))
        except Exception:
            continue
    # newest first
    events.sort(key=lambda e: (e.day, e.time), reverse=True)
    return events[:max_events]
