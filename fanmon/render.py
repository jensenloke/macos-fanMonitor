"""Render a full dashboard frame with rich."""
from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box

from .procs import CATEGORY_AGENT, CATEGORY_BROWSER, CATEGORY_CHAT, CATEGORY_APP

_SEV_COLOR = {"ok": "green", "watch": "yellow", "high": "red"}
_KIND_ICON = {"memory": "💾", "cpu": "🔥", "mixed": "🔀", "watch": "👀", "healthy": "✅"}
_CAT_COLOR = {
    CATEGORY_AGENT: "magenta",
    CATEGORY_BROWSER: "cyan",
    CATEGORY_CHAT: "blue",
    CATEGORY_APP: "white",
}


def _bar(frac: float, width: int = 22) -> Text:
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    color = "green" if frac < 0.4 else ("yellow" if frac < 0.75 else "red")
    t = Text()
    t.append("█" * filled, style=color)
    t.append("░" * (width - filled), style="grey35")
    return t


def _fan_panel(snap) -> Panel:
    fan = snap["fan"]
    temps = snap["temps"]
    mem = snap["mem"]
    t = Table.grid(padding=(0, 2))
    t.add_column(justify="right", style="bold grey70")
    t.add_column()

    duty = fan.duty if fan else 0.0
    fan_line = Text()
    fan_line.append(f"{fan.rpm:,.0f} RPM ", style="bold")
    fan_line.append_text(_bar(duty))
    fan_line.append(f"  {duty*100:3.0f}% duty", style="grey62")
    fan_line.append(f"  (target {fan.target:,.0f}, max {fan.max_rpm:,.0f}, {fan.mode})",
                     style="grey50")
    t.add_row("FAN", fan_line)

    if temps and temps.hottest_c:
        temp_line = Text()
        temp_line.append(f"{temps.hottest_c:.1f}°C ", style="bold")
        temp_line.append(f"[{temps.hottest_key}] ", style="grey50")
        parts = []
        for key, (label, c) in list(temps.notable.items())[:4]:
            if key != temps.hottest_key:
                parts.append(f"{label} {c:.0f}°")
        if parts:
            temp_line.append("·  ".join(parts), style="grey62")
        t.add_row("TEMP", temp_line)

    l1, l5, l15 = snap["load1"], snap["load5"], snap["load15"]
    cores = snap["cores"]
    load_line = Text()
    load_line.append(f"{l1:.2f} / {l5:.2f} / {l15:.2f}", style="bold")
    load_line.append(f"   on {cores} cores", style="grey62")
    load_frac = l1 / (cores or 1)
    load_line.append("   ")
    load_line.append_text(_bar(load_frac / 2.0, 14))  # scale: full at load=2*cores
    t.add_row("LOAD", load_line)

    swap_pct = mem["swap_used_pct"]
    mem_line = Text()
    mem_line.append(f"swap {mem['swap_used_gb']:.1f}/{mem['swap_total_gb']:.1f} GB ",
                    style="bold")
    mem_line.append(f"({swap_pct:.0f}%)", style=_sev_for_swap(swap_pct))
    mem_line.append(f"  ·  compressor x{mem['comp_ratio']:.1f}", style="grey62")
    if mem.get("free_pct") is not None:
        mem_line.append(f"  ·  RAM free {mem['free_pct']}%", style="grey62")
    t.add_row("MEM", mem_line)

    return Panel(t, title="macOS Fan Monitor", border_style="blue",
                 subtitle=snap["header_sub"], expand=True)


def _sev_for_swap(pct):
    return "green" if pct < 50 else ("yellow" if pct < 80 else "red")


def _verdict_panel(snap) -> Panel:
    v = snap["verdict"]
    color = _SEV_COLOR.get(v.severity, "white")
    icon = _KIND_ICON.get(v.kind, "•")
    body = Text()
    body.append(f"{icon}  ", style=color)
    body.append(v.headline, style=f"bold {color}")
    body.append("\n")
    body.append(v.detail, style="grey74")
    return Panel(body, title="Verdict — why is the fan spinning?",
                 border_style=color, expand=True)


def _rec_panel(snap) -> Panel:
    recs = snap["recs"]
    if not recs:
        body = Text("Nothing to close — system looks healthy.", style="green")
        return Panel(body, title="Recommended to close", border_style="green",
                     expand=True)
    t = Table(box=box.SIMPLE_HEAVY, expand=True, pad_edge=False)
    t.add_column("#", style="grey50", width=2)
    t.add_column("process / group", overflow="fold")
    t.add_column("RSS", justify="right")
    t.add_column("CPU", justify="right")
    t.add_column("age", justify="right")
    t.add_column("why", overflow="fold")
    for i, r in enumerate(recs, 1):
        cat_color = _CAT_COLOR.get(r.category, "white")
        name = Text(r.label, style=cat_color)
        t.add_row(
            str(i), name,
            f"{r.rss_mb:,.0f} MB",
            f"{r.cpu_pct:,.0f}%",
            f"{r.age_h:,.1f} h",
            Text(r.reason, style="grey62"),
        )
    sub = "ranked by the active regime's weights — verify before killing"
    return Panel(t, title="Recommended to close", border_style="yellow",
                 subtitle=sub, expand=True)


def _top_table(procs, key, title, color, n=7) -> Panel:
    ranked = sorted(procs, key=key, reverse=True)[:n]
    t = Table(box=box.SIMPLE, expand=True, pad_edge=False)
    t.add_column("PID", style="grey50", width=7)
    t.add_column("process", overflow="fold")
    t.add_column("CPU", justify="right")
    t.add_column("RSS", justify="right")
    for p in ranked:
        t.add_row(
            str(p.pid),
            Text(p.comm[:28], style=_CAT_COLOR.get(p.category, "white")),
            f"{p.cpu_pct:,.0f}%",
            f"{p.rss_mb:,.0f}",
        )
    return Panel(t, title=title, border_style=color, expand=True)


def _watchdog_panel(snap) -> Panel:
    wd = snap["watchdog"]
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold grey70", justify="right")
    t.add_column(overflow="fold")

    state_color = {"OK": "green", "WARN": "yellow", "CRIT": "red"}.get(
        wd.probe_state, "grey50")
    t.add_row("probe", Text(f"fan-activity {wd.probe_state}", style=f"bold {state_color}"))
    t.add_row("thresholds",
              Text(f"trigger ≥{wd.trigger_rpm} RPM · re-arm ≤{wd.reset_rpm} RPM",
                   style="grey62"))
    for e in wd.events[:6]:
        rpm_style = "red" if e.rpm >= wd.trigger_rpm else "grey62"
        t.add_row(
            f"{e.day[5:]} {e.time}",
            Text.assemble(
                (f"{e.rpm:>5} RPM ", rpm_style),
                (e.detail[:70], "grey58"),
            ),
        )
    if not wd.events:
        t.add_row("events", Text("no fan events logged yet", style="grey50"))
    return Panel(t, title="Watchdog fan history", border_style="cyan", expand=True)


def build(snap) -> Group:
    top_cpu = _top_table(snap["procs"], key=lambda p: p.cpu_pct,
                         title="Top CPU (real delta)", color="red")
    top_mem = _top_table(snap["procs"], key=lambda p: p.rss_mb,
                         title="Top memory (resident)", color="blue")
    middle = Columns([top_cpu, top_mem], equal=True, expand=True, padding=(0, 1))
    advisories = snap.get("advisories") or []
    parts = [
        _fan_panel(snap),
        _verdict_panel(snap),
        _rec_panel(snap),
        middle,
        _watchdog_panel(snap),
    ]
    if advisories:
        adv = Text("\n".join("• " + a for a in advisories), style="grey74")
        parts.insert(3, Panel(adv, title="System daemons (not closeable)",
                              border_style="grey50", expand=True))
    return Group(*parts)
