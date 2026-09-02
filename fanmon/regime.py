"""Regime detection and the close-recommendation algorithm.

The core insight this tool encodes (learned from real incidents):
a spinning fan on this Mac is caused by one of two very different things,
and the fix for each is different.

  1. CPU regime  - something is genuinely computing. Load is high AND
                   measured CPU% is high. Fix: close / wait on the hog.

  2. MEMORY regime (swap thrash) - the system ran out of RAM and is
                   paging. Load is high but measured CPU% is LOW because
                   processes are blocked on disk I/O, not computing.
                   `ps %cpu` and the watchdog's "top CPU" both MISS this.
                   Fix: close memory hogs to stop the thrash.

The algorithm decides which regime is active, then ranks closeable
processes with weights appropriate to that regime.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .procs import Proc, CATEGORY_AGENT, CATEGORY_BROWSER, CATEGORY_CHAT, \
    CATEGORY_SYSTEM, CATEGORY_APP


# --- verdict --------------------------------------------------------------

@dataclass
class Verdict:
    kind: str                 # "memory" | "cpu" | "mixed" | "healthy"
    headline: str
    detail: str
    severity: str = "ok"      # "ok" | "watch" | "high"


def verdict(procs: list[Proc], mem: dict, fan, temps, load1: float, cores: int,
            thermal=None, cpu=None) -> Verdict:
    """Name the active regime.

    `thermal` (pmset throttle state) and `cpu` (per-core utilisation) are
    optional; with them the verdict works on fanless MacBook Airs, where
    "the fan is spinning" has no meaning but "macOS is throttling" does.
    """
    cpu_busy = sum(p.cpu_pct for p in procs)      # % of one core
    capacity = cores * 100.0
    cpu_frac = (cpu_busy / capacity) if capacity else 0.0
    if cpu is not None and getattr(cpu, "available", False):
        # Per-core ticks are the more honest capacity measure when present.
        cpu_frac = max(cpu_frac, cpu.total_pct / 100.0)

    swap_pct = mem["swap_used_pct"]
    comp_ratio = mem["comp_ratio"]
    free_pct = mem.get("free_pct")
    free_pct = free_pct if free_pct is not None else 100
    fanless = bool(fan is not None and getattr(fan, "fanless", False))
    fan_duty = fan.duty if fan else 0.0
    throttle = thermal.throttle_pct if thermal is not None else 0
    heat = "your Mac is hot" if fanless else "fan is spinning"

    memory_pressure = (
        swap_pct >= 70 or comp_ratio >= 4.0 or free_pct <= 10
    )
    cpu_pressure = cpu_frac >= 0.55 or any(p.cpu_pct >= 90 for p in procs)
    load_pressure = load1 >= cores * 0.9

    if memory_pressure and cpu_pressure:
        return Verdict(
            "mixed",
            "Memory pressure + active CPU load",
            f"Swap {swap_pct:.0f}% used with {cpu_busy:.0f}% of a core busy. "
            f"Both paging and compute are heating the machine.",
            "high",
        )
    if memory_pressure and load_pressure and not cpu_pressure:
        return Verdict(
            "memory",
            f"Swap thrash - {heat} from memory pressure, not CPU",
            f"Swap {swap_pct:.0f}% used, compressor x{comp_ratio:.1f}, "
            f"load {load1:.1f} on {cores} cores but only {cpu_busy:.0f}% of a "
            f"core busy. Processes are blocked on disk, not computing. "
            f"Close memory hogs below to stop the thrash.",
            "high",
        )
    if cpu_pressure:
        top = max(procs, key=lambda p: p.cpu_pct)
        return Verdict(
            "cpu",
            f"CPU load - {top.comm} is the biggest contributor",
            f"{cpu_busy:.0f}% of a core busy ({cpu_frac*100:.0f}% of capacity). "
            f"Top: {top.comm} at {top.cpu_pct:.0f}%.",
            "watch" if cpu_frac < 0.8 else "high",
        )
    if throttle >= 10:
        cooling = ("passive cooling can't keep up" if fanless
                   else "even with the fan running")
        return Verdict(
            "thermal",
            f"CPU throttled to {100 - throttle}% - {cooling}",
            f"macOS is holding the CPU clock back {throttle}% (pmset "
            f"CPU_Speed_Limit). No single hog is computing right now, so the "
            f"heat is residual; let it cool, or close the largest processes.",
            "high" if throttle >= 30 else "watch",
        )
    if not fanless and fan_duty >= 0.4:
        return Verdict(
            "watch",
            "Fan elevated but no clear single cause",
            f"Fan at {fan_duty*100:.0f}% duty. Heat may be residual from a "
            f"recent burst; watch the next few samples.",
            "watch",
        )
    cooling = ("no throttling" if fanless
               else f"fan {fan_duty*100:.0f}% duty")
    return Verdict(
        "healthy",
        "Nominal - no runaway CPU, no memory thrash",
        f"Swap {swap_pct:.0f}%, load {load1:.1f}/{cores}, {cooling}.",
        "ok",
    )


# --- recommendation -------------------------------------------------------

@dataclass
class Rec:
    label: str
    category: str
    rss_mb: float
    cpu_pct: float
    age_h: float
    pids: list = field(default_factory=list)
    count: int = 1
    score: float = 0.0
    reason: str = ""


def recommend(procs: list[Proc], v: Verdict, top_n: int = 6) -> list[Rec]:
    """Rank closeable processes/groups appropriate to the active regime."""
    # Group swarm siblings and duplicates together.
    groups: dict = {}
    for p in procs:
        if not p.closeable or p.category == CATEGORY_SYSTEM:
            continue
        g = groups.setdefault(p.group, [])
        g.append(p)

    # Weighting per regime.
    if v.kind == "memory":
        w_rss, w_cpu, w_age = 1.0, 0.05, 6.0
        why = "frees RAM driving swap thrash"
    elif v.kind == "cpu":
        w_rss, w_cpu, w_age = 0.02, 1.0, 1.0
        why = "burning CPU now"
    elif v.kind == "mixed":
        w_rss, w_cpu, w_age = 0.8, 0.6, 4.0
        why = "contributing to memory + CPU load"
    else:
        w_rss, w_cpu, w_age = 0.5, 0.3, 2.0
        why = "large / long-running"

    recs = []
    for group, members in groups.items():
        rss = sum(m.rss_mb for m in members)
        cpu = sum(m.cpu_pct for m in members)
        age_h = max(m.age_h for m in members)
        cat = members[0].category
        # Category prior: agents/browsers are the usual suspects here.
        cat_prior = {
            CATEGORY_AGENT: 1.0,
            CATEGORY_BROWSER: 0.85,
            CATEGORY_CHAT: 0.6,
            CATEGORY_APP: 0.5,
        }.get(cat, 0.4)
        score = (rss * w_rss + cpu * w_cpu + age_h * w_age) * cat_prior
        if score <= 0:
            continue
        label = group if len(members) == 1 else f"{group} x{len(members)}"
        recs.append(Rec(
            label=label, category=cat, rss_mb=rss, cpu_pct=cpu,
            age_h=age_h, pids=[m.pid for m in members],
            count=len(members), score=score, reason=why,
        ))

    recs.sort(key=lambda r: r.score, reverse=True)
    return recs[:top_n]


# --- advisory for protected-but-hot processes -----------------------------

def system_advisories(procs: list[Proc]) -> list[str]:
    """When a protected/symptom process is hot, explain rather than 'close it'."""
    notes = []
    for p in procs:
        if p.category != CATEGORY_SYSTEM:
            continue
        if p.cpu_pct >= 60:
            if "WindowServer" in p.command:
                notes.append(
                    f"WindowServer at {p.cpu_pct:.0f}% - compositor load. "
                    f"Reduce open windows / external displays; it is not closeable."
                )
            elif "mds" in p.comm or "spotlight" in p.command.lower():
                notes.append(
                    f"Spotlight ({p.comm}) at {p.cpu_pct:.0f}% - indexing burst, "
                    f"usually self-resolves in minutes."
                )
            elif "suggestd" in p.comm:
                notes.append(
                    f"suggestd at {p.cpu_pct:.0f}% - Siri suggestions burst, "
                    f"self-resolves."
                )
            else:
                notes.append(
                    f"{p.comm} at {p.cpu_pct:.0f}% - system daemon, not closeable."
                )
    return notes
