"""Threshold triggers that auto-start an AI consult.

Each rule arms when its metric crosses the threshold, fires once, then stays
quiet until BOTH the cooldown has elapsed AND the metric has dropped below
0.85 x threshold. Evaluation is a cheap read of the snap dict — it runs on
the UI thread every refresh.
"""
from __future__ import annotations

import time

from .config import AiConfig


class TriggerMonitor:
    def __init__(self, cfg: AiConfig):
        self.cfg = cfg
        self._fired: dict = {}          # rule name -> True while "spent"
        self._fired_at: dict = {}
        self._high_streak = 0
        self.last_fired_at = 0.0
        self.last_reason = ""

    def update(self, snap: dict) -> str | None:
        """Name of the trigger that fired, or None."""
        now = time.time()
        t = self.cfg.triggers
        v = snap["verdict"]
        self._high_streak = (self._high_streak + 1
                             if v.severity == "high" else 0)
        rules = self._rules(snap, t)
        for name, value, thr in rules:
            if self._cooling(now, name):
                continue
            if self._fired.get(name):
                if self._rearmable(name, value, thr):
                    self._fired[name] = False
                continue
            if value >= thr:
                self._fired[name] = True
                self._fired_at[name] = now
                self.last_fired_at = now
                self.last_reason = f"{name} {value:.0f}% >= {thr}%"
                return self.last_reason
        name = "high severity"
        if self._fired.get(name):
            if self._high_streak == 0 and self._cooled(now, name):
                self._fired[name] = False
        elif (not self._cooling(now, name)
              and self._high_streak >= t.high_severity_samples):
            self._fired[name] = True
            self._fired_at[name] = now
            self.last_fired_at = now
            self.last_reason = (f"severity 'high' for {self._high_streak} "
                                f"consecutive samples")
            return self.last_reason
        return None

    def _rules(self, snap: dict, t) -> list:
        fan, mem, therm = snap["fan"], snap["mem"], snap["thermal"]
        rules = [
            ("throttle", therm.throttle_pct, t.throttle_pct),
            ("memory used", mem["used_pct"], t.mem_used_pct),
            ("swap used", mem["swap_used_pct"], t.swap_used_pct),
        ]
        if not fan.fanless:
            rules.insert(0, ("fan duty", fan.duty * 100, t.fan_duty_pct))
        return rules

    def _cooling(self, now: float, name: str) -> bool:
        return now - self._fired_at.get(name, 0) < self.cfg.cooldown_s

    def _cooled(self, now: float, name: str) -> bool:
        return not self._cooling(now, name)

    def _rearmable(self, name: str, value: float, thr: float) -> bool:
        return (value < 0.85 * thr
                and not self._cooling(time.time(), name))
