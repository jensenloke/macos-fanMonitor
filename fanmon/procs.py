"""Process snapshot with CPU-time delta and closeability classification.

CPU% here is a real delta over the sampling window (from `time`),
NOT the stale lifetime average that `ps %cpu` reports.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field

# A process class the algorithm may recommend closing.
CATEGORY_AGENT = "agent"      # claude / codex / omp / devin / node_repl
CATEGORY_BROWSER = "browser"
CATEGORY_CHAT = "chat"
CATEGORY_APP = "app"          # other user apps
CATEGORY_SYSTEM = "system"    # never recommend closing
CATEGORY_KERNEL = "kernel"


@dataclass
class Proc:
    pid: int
    ppid: int
    comm: str
    command: str
    rss_mb: float
    age_s: float
    cpu_pct: float = 0.0
    category: str = CATEGORY_APP
    closeable: bool = True
    session: str = ""
    group: str = ""

    @property
    def age_h(self) -> float:
        return self.age_s / 3600.0


# --- classification -------------------------------------------------------

# System / protected: symptoms, not causes. Never recommend closing.
_PROTECTED = re.compile(
    r"(?i)(kernel_task|launchd|/sbin/|/usr/libexec/|WindowServer|"
    r"WindowManager|mds$|mds_stores|mdworker|spotlightknowledged|"
    r"suggestd|mediaanalysisd|fileproviderd|bird|cfprefsd|"
    r"opendirectoryd|configd|powerd|loginwindow|Dock|"
    r"SystemUIServer|airportd|ContinuityCapture|com\.apple\.|"
    r"/System/Library/|/usr/sbin/|/usr/libexec|UserEventAgent|"
    r"distnoted|nsurlsessiond|nsurlstoraged|securityd|syslogd)"
)

_AGENT = re.compile(
    r"(?i)(claude|codex|ChatGPT|\bomp\b|cli\.js|devin|cmux|sinter|"
    r"node_repl|claude-swarm|anthropic|openai|cursor|aider)"
)

_BROWSER = re.compile(
    r"(?i)(Google Chrome|Chrome Helper|Microsoft Edge|Safari|Arc|"
    r"Firefox|Brave|Chromium|Vivaldi)"
)

_CHAT = re.compile(
    r"(?i)(WhatsApp|Telegram|Discord|Slack|Microsoft Teams|MSTeams|"
    r"Zoom|Signal|Messenger|WeChat)"
)

_SESSION = re.compile(r"session-([0-9a-f]{8})")


def classify(command: str, comm: str):
    """Return (category, closeable)."""
    c = command or comm
    if _PROTECTED.search(c):
        return CATEGORY_SYSTEM, False
    if _AGENT.search(c):
        return CATEGORY_AGENT, True
    if _BROWSER.search(c):
        return CATEGORY_BROWSER, True
    if _CHAT.search(c):
        return CATEGORY_CHAT, True
    # Anything in /Applications is a user app; closeable but low priority.
    if c.startswith("/Applications"):
        return CATEGORY_APP, True
    return CATEGORY_APP, False


# --- time parsing ---------------------------------------------------------

def _etime_to_s(e: str) -> float:
    e = e.strip()
    days = 0
    if "-" in e:
        d, e = e.split("-", 1)
        try:
            days = int(d)
        except ValueError:
            days = 0
    parts = e.split(":")
    try:
        parts = [float(x) for x in parts]
    except ValueError:
        return 0.0
    if len(parts) == 3:
        s = parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        s = parts[0] * 60 + parts[1]
    else:
        s = parts[0] if parts else 0.0
    return days * 86400 + s


def _cputime_to_s(t: str) -> float:
    parts = t.split(":")
    try:
        parts = [float(x) for x in parts]
    except ValueError:
        return 0.0
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] if parts else 0.0


# --- sampler --------------------------------------------------------------

class ProcSampler:
    def __init__(self):
        self.prev: dict = {}   # pid -> cpu_seconds
        self.prev_t: float | None = None

    def sample(self) -> list[Proc]:
        out = subprocess.run(
            ["ps", "-axww", "-o", "pid=,ppid=,rss=,etime=,time=,command="],
            capture_output=True, text=True,
        ).stdout
        now = time.time()
        dt = (now - self.prev_t) if self.prev_t else None
        procs: list[Proc] = []
        for line in out.splitlines():
            parts = line.split(None, 5)
            if len(parts) < 6:
                continue
            pid_s, ppid_s, rss_s, etime, ctime, command = parts
            try:
                pid = int(pid_s)
                ppid = int(ppid_s)
                rss_kb = int(rss_s)
            except ValueError:
                continue
            cpu_s = _cputime_to_s(ctime)
            cpu_pct = 0.0
            if dt and pid in self.prev:
                cpu_pct = max(0.0, (cpu_s - self.prev[pid]) / dt * 100.0)
            self.prev[pid] = cpu_s
            toks = command.split()
            comm = (toks[0].split("/")[-1] if toks else "?")[:26] or "?"
            cat, closeable = classify(command, comm)
            session = ""
            if m := _SESSION.search(command):
                session = m.group(1)
            procs.append(Proc(
                pid=pid, ppid=ppid, comm=comm, command=command,
                rss_mb=rss_kb / 1024.0, age_s=_etime_to_s(etime),
                cpu_pct=cpu_pct, category=cat, closeable=closeable,
                session=session, group=_group_key(comm, cat, session),
            ))
        self.prev_t = now
        return procs


def _group_key(comm: str, cat: str, session: str) -> str:
    """Group swarm siblings so we recommend closing them as a batch."""
    if cat == CATEGORY_AGENT and session:
        return f"{comm}@{session}"
    return comm
