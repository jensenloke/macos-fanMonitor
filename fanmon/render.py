"""Render a full dashboard frame with rich (used by `fm --once`)."""
from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box

from . import brand
from .procs import CATEGORY_AGENT, CATEGORY_BROWSER, CATEGORY_CHAT, CATEGORY_APP

_KIND_ICON = {"memory": "💾", "cpu": "🔥", "mixed": "🔀", "watch": "👀",
              "thermal": "🌡️", "healthy": "✅"}
_CAT_COLOR = {
    CATEGORY_AGENT: brand.SALMON,
    CATEGORY_BROWSER: brand.PEACH,
    CATEGORY_CHAT: "#C9A0DC",
    CATEGORY_APP: brand.MIST,
}
_BORDER = brand.RUST


def _gauges(snap) -> Table:
    fan, temps, mem, cpu, therm = (snap["fan"], snap["temps"], snap["mem"],
                                   snap["cpu"], snap["thermal"])
    t = Table.grid(padding=(0, 2))
    t.add_column(justify="right", style=f"bold {brand.SALMON}")
    t.add_column()

    throttle = therm.throttle_pct
    if fan.fanless:
        line = Text()
        line.append("passive · no fan   ", style="bold")
        line.append_text(brand.bar(throttle / 100, 16))
        line.append(f"  throttled {throttle}%" if throttle else "  not throttled",
                    style=(brand.SAGE if throttle == 0 else
                           brand.PEACH if throttle < 30 else brand.CORAL))
        t.add_row("COOLING", line)
    else:
        duty = fan.duty
        line = Text()
        line.append(f"{fan.rpm:,.0f} RPM ", style="bold")
        line.append_text(brand.bar(duty, 16))
        line.append(f"  {duty*100:3.0f}% duty", style=brand.heat_color(duty))
        if fan.present is None:
            line.append("  (no SMC reader — install Stats.app)", style=brand.MUTED)
        else:
            line.append(f"  target {fan.target:,.0f}", style=brand.MUTED)
            if therm.known:
                line.append(f" · CPU speed {100 - throttle}%", style=brand.MUTED)
        t.add_row("FAN", line)

    if temps and temps.hottest_c:
        line = Text()
        line.append(f"{temps.hottest_c:.1f}°C ",
                    style=f"bold {brand.heat_color((temps.hottest_c - 40) / 60)}")
        line.append(f"[{temps.hottest_key}]  ", style=brand.MUTED)
        parts = [f"{label} {c:.0f}°"
                 for key, (label, c) in list(temps.notable.items())[:4]
                 if key != temps.hottest_key]
        line.append("·  ".join(parts), style=brand.MUTED)
        t.add_row("TEMP", line)

    l1, l5, l15 = snap["load1"], snap["load5"], snap["load15"]
    cores = snap["cores"]
    line = Text()
    if cpu.available:
        line.append(f"{cpu.total_pct:.0f}% ",
                    style=f"bold {brand.heat_color(cpu.total_pct / 100)}")
        line.append_text(brand.bar(cpu.total_pct / 100, 16))
        if cpu.e_cores:
            line.append(f"  P {cpu.p_busy:.0f}%  E {cpu.e_busy:.0f}%", style=brand.MUTED)
    line.append(f"  load {l1:.2f} / {l5:.2f} / {l15:.2f} on {cores} cores",
                style=brand.MUTED)
    t.add_row("CPU", line)

    used = mem["used_pct"] / 100.0
    line = Text()
    line.append(f"{mem['used_gb']:.1f}/{mem['total_gb']:.0f} GB ", style="bold")
    line.append_text(brand.bar(used, 16))
    line.append(f"  {used*100:3.0f}%", style=brand.heat_color(used))
    swap_pct = mem["swap_used_pct"]
    line.append(f"  swap {mem['swap_used_gb']:.1f}/{mem['swap_total_gb']:.0f} GB ",
                style=brand.MUTED)
    line.append(f"{swap_pct:.0f}%", style=brand.heat_color(swap_pct / 100))
    line.append(f" · comp x{mem['comp_ratio']:.1f}", style=brand.MUTED)
    t.add_row("MEMORY", line)
    return t


def _header_panel(snap) -> Panel:
    grid = Table.grid(padding=(0, 3))
    grid.add_column(width=brand.BRAND_WIDTH)
    grid.add_column()
    grid.add_row(brand.brand_block(), _gauges(snap))
    return Panel(
        grid,
        title=f"[bold {brand.PEACH}]Fan Monitor - Agentic Builders Collective[/]",
        subtitle=Text(snap["header_sub"], style=brand.MUTED),
        border_style=_BORDER,
        expand=True,
    )


def _verdict_panel(snap) -> Panel:
    v = snap["verdict"]
    color = brand.SEVERITY.get(v.severity, brand.MIST)
    icon = _KIND_ICON.get(v.kind, "•")
    body = Text()
    body.append(f"{icon}  ", style=color)
    body.append(v.headline, style=f"bold {color}")
    body.append("\n")
    body.append(v.detail, style=brand.MIST)
    question = "why is my Mac hot?" if snap["fanless"] else "why is the fan spinning?"
    return Panel(body, title=f"Verdict — {question}", border_style=color, expand=True)


def _rec_panel(snap) -> Panel:
    recs = snap["recs"]
    if not recs:
        body = Text("Nothing to close — system looks healthy.", style=brand.SAGE)
        return Panel(body, title="Recommended to close", border_style=brand.SAGE,
                     expand=True)
    t = Table(box=box.SIMPLE_HEAVY, expand=True, pad_edge=False)
    t.add_column("#", style=brand.MUTED, width=2)
    t.add_column("process / group", overflow="fold")
    t.add_column("RSS", justify="right")
    t.add_column("CPU", justify="right")
    t.add_column("age", justify="right")
    t.add_column("why", overflow="fold")
    for i, r in enumerate(recs, 1):
        t.add_row(
            str(i), Text(r.label, style=_CAT_COLOR.get(r.category, brand.MIST)),
            f"{r.rss_mb:,.0f} MB",
            f"{r.cpu_pct:,.0f}%",
            f"{r.age_h:,.1f} h",
            Text(r.reason, style=brand.MUTED),
        )
    sub = "ranked by the active regime's weights — verify before killing"
    return Panel(t, title="Recommended to close", border_style=brand.PEACH,
                 subtitle=sub, expand=True)


def _cpu_panel(snap) -> Panel:
    cpu = snap["cpu"]
    if not cpu.available:
        return Panel(Text("per-core data unavailable", style=brand.MUTED),
                     title="CPU cores", border_style=_BORDER, expand=True)
    t = Text()
    for pct, label in zip(cpu.per_core, cpu.labels):
        t.append(f"{label:>3} ", style=brand.MUTED)
        t.append_text(brand.bar(pct / 100, 18))
        t.append(f" {pct:3.0f}%\n", style=brand.heat_color(pct / 100))
    t.append(f"user {cpu.user_pct:.0f}% · sys {cpu.sys_pct:.0f}%", style=brand.MUTED)
    if cpu.e_cores:
        t.append(" · P = performance, E = efficiency", style=brand.MUTED)
    return Panel(t, title="CPU cores", border_style=_BORDER, expand=True)


def _mem_panel(snap) -> Panel:
    mem = snap["mem"]
    total = mem["total_gb"] or 1.0
    t = Text()
    for name, gb, color in (
        ("app", mem["app_gb"], brand.SALMON),
        ("wired", mem["wired_gb"], brand.PEACH),
        ("compressed", mem["comp_occupied_gb"], brand.CORAL),
        ("cached", mem["cached_gb"], brand.RUST),
    ):
        t.append(f"{name:>10} ", style=brand.MUTED)
        t.append_text(brand.bar(gb / total, 18, color=color))
        t.append(f" {gb:5.1f} GB\n", style="bold")
    t.append(f"{'swap':>10} ", style=brand.MUTED)
    t.append_text(brand.bar(mem["swap_used_pct"] / 100, 18))
    t.append(f" {mem['swap_used_gb']:5.1f} GB\n", style="bold")
    free = mem.get("free_pct")
    t.append(f"free {free}% · " if free is not None else "", style=brand.MUTED)
    t.append(f"page in {mem['pagein_rate']:.0f}/s · out {mem['pageout_rate']:.0f}/s",
             style=brand.MUTED)
    return Panel(t, title="Memory", border_style=_BORDER, expand=True)


def _top_table(procs, key, title, color, n=7) -> Panel:
    ranked = sorted(procs, key=key, reverse=True)[:n]
    t = Table(box=box.SIMPLE, expand=True, pad_edge=False)
    t.add_column("PID", style=brand.MUTED, width=7)
    t.add_column("process", overflow="fold")
    t.add_column("CPU", justify="right")
    t.add_column("RSS", justify="right")
    for p in ranked:
        t.add_row(
            str(p.pid),
            Text(p.comm[:28], style=_CAT_COLOR.get(p.category, brand.MIST)),
            f"{p.cpu_pct:,.0f}%",
            f"{p.rss_mb:,.0f}",
        )
    return Panel(t, title=title, border_style=color, expand=True)


def _watchdog_panel(snap) -> Panel:
    wd = snap["watchdog"]
    t = Table.grid(padding=(0, 2))
    t.add_column(style=f"bold {brand.MUTED}", justify="right")
    t.add_column(overflow="fold")

    state_color = {"OK": brand.SAGE, "WARN": brand.PEACH,
                   "CRIT": brand.CORAL}.get(wd.probe_state, brand.MUTED)
    t.add_row("probe", Text(f"fan-activity {wd.probe_state}",
                            style=f"bold {state_color}"))
    t.add_row("thresholds",
              Text(f"trigger ≥{wd.trigger_rpm} RPM · re-arm ≤{wd.reset_rpm} RPM",
                   style=brand.MUTED))
    for e in wd.events[:6]:
        rpm_style = brand.CORAL if e.rpm >= wd.trigger_rpm else brand.MUTED
        t.add_row(
            f"{e.day[5:]} {e.time}",
            Text.assemble((f"{e.rpm:>5} RPM ", rpm_style),
                          (e.detail[:70], brand.MUTED)),
        )
    if not wd.events:
        t.add_row("events", Text("no fan events logged yet", style=brand.MUTED))
    return Panel(t, title="Watchdog fan history", border_style=_BORDER, expand=True)


def build(snap) -> Group:
    top_cpu = _top_table(snap["procs"], key=lambda p: p.cpu_pct,
                         title="Top CPU (real delta)", color=brand.CORAL)
    top_mem = _top_table(snap["procs"], key=lambda p: p.rss_mb,
                         title="Top memory (resident)", color=brand.SALMON)
    advisories = snap.get("advisories") or []
    parts = [
        _header_panel(snap),
        _verdict_panel(snap),
        _rec_panel(snap),
        Columns([_cpu_panel(snap), _mem_panel(snap)], equal=True, expand=True,
                padding=(0, 1)),
        Columns([top_cpu, top_mem], equal=True, expand=True, padding=(0, 1)),
        _watchdog_panel(snap),
    ]
    if advisories:
        adv = Text("\n".join("• " + a for a in advisories), style=brand.MIST)
        parts.insert(3, Panel(adv, title="System daemons (not closeable)",
                              border_style=brand.MUTED, expand=True))
    return Group(*parts)
