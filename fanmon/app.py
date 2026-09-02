"""Textual TUI app — a lazygit/yazi-style terminal application.

Layout:
  ┌ ABC boot (while the first sample loads) ────────────────────┐
  ┌ branded header ─────────────────────────────────────────────┐
  │ FAN / COOLING · TEMP · CPU · MEMORY  (gauges)               │
  ├ verdict ────────────────────────────────────────────────────┤
  │ why is the fan spinning / my Mac hot?  (+ daemon advisories)│
  ├ tabs ───────────────────────────────────────────────────────┤
  │ Close | CPU | Memory | Processes | Watchdog                  │
  ├ footer ─────────────────────────────────────────────────────┤
  └─────────────────────────────────────────────────────────────┘

Keys:
  q / ctrl+q  quit          r  refresh now
  [ / ]       previous / next tab
  1 / 2 / 3   sort processes by CPU / memory / age
  k           SIGTERM the selected row (confirm prompt)
  tab         move focus between panes
"""
from __future__ import annotations

import os
import signal
import time

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    DataTable, Footer, Header, Label, ProgressBar, Sparkline, Static,
    TabbedContent, TabPane,
)
from textual.worker import Worker, WorkerState

from . import brand
from .engine import Engine
from .procs import Proc
from .regime import Rec


_KIND_ICON = {"memory": "💾", "cpu": "🔥", "mixed": "🔀", "watch": "👀",
              "thermal": "🌡️", "healthy": "✅"}
_TOP_N_PROCS = 80
_TOP_N_TAB = 14
_TABS = ["tab-close", "tab-cpu", "tab-mem", "tab-procs", "tab-watchdog"]
_BOOT_MIN_SECONDS = 3.0
_SPARK = "▁▂▃▄▅▆▇█"


# --- boot screen ----------------------------------------------------------

class BrandBoot(Screen):
    DEFAULT_CSS = """
    BrandBoot {
        background: $background;
        align: center middle;
    }
    #boot-box {
        width: 47;
        height: 15;
        border: round $secondary;
        padding: 1 2;
        align: center middle;
    }
    #boot-mark {
        width: 27;
        height: 7;
        margin-left: 7;
    }
    #boot-product {
        height: 1;
        margin-top: 1;
        text-align: center;
        color: $primary;
        text-style: bold;
    }
    #boot-status {
        height: 1;
        margin-top: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self):
        super().__init__()
        self._step = 0
        self._status_step = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="boot-box"):
            yield Static(brand.brand_frame("reveal", 0), id="boot-mark")
            yield Static("FAN MONITOR", id="boot-product")
            yield Static("reading local Mac signals", id="boot-status")

    def on_mount(self) -> None:
        self.set_interval(brand.REVEAL_PERIOD, self._tick)

    def _tick(self) -> None:
        self._step += 1
        mark = self.query_one("#boot-mark", Static)
        if self._step < brand.REVEAL_STEPS:
            mark.update(brand.brand_frame("reveal", self._step))
        else:
            mark.update(brand.brand_block())
        self._status_step = (self._status_step + 1) % 4
        dots = " ·" * self._status_step
        self.query_one("#boot-status", Static).update(
            Text(f"reading local Mac signals{dots}", style=brand.MUTED))


# --- confirmation modal ---------------------------------------------------

class ConfirmKill(ModalScreen[bool]):
    BINDINGS = [
        Binding("y", "yes", "Yes, terminate", show=True),
        Binding("n", "no", "No", show=True),
        Binding("escape", "no", "Cancel", show=False),
    ]

    def __init__(self, label: str, pids: list[int]):
        super().__init__()
        self.label = label
        self.pids = pids

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(
                Text.assemble(
                    ("Terminate ", f"bold {brand.PEACH}"),
                    (self.label, "bold"),
                    (" ?", f"bold {brand.PEACH}"),
                )
            )
            pids_str = ", ".join(map(str, self.pids[:6]))
            if len(self.pids) > 6:
                pids_str += " …"
            yield Static(
                f"SIGTERM → {len(self.pids)} process(es): {pids_str}",
                classes="dim",
            )
            with Horizontal(id="confirm-btns"):
                yield Static("[y] yes, terminate", classes="btn yes")
                yield Static("[n] no", classes="btn no")

    def action_yes(self):
        self.dismiss(True)

    def action_no(self):
        self.dismiss(False)


# --- the app --------------------------------------------------------------

class FanMonitorApp(App):
    TITLE = "Fan Monitor - Agentic Builders Collective"
    SUB_TITLE = ""
    CSS_PATH = "fanmon.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("left_square_bracket", "prev_tab", "Prev tab", show=True,
                key_display="["),
        Binding("right_square_bracket", "next_tab", "Next tab", show=True,
                key_display="]"),
        Binding("1", "sort_cpu", "Sort CPU", show=True),
        Binding("2", "sort_mem", "Sort Mem", show=True),
        Binding("3", "sort_age", "Sort Age", show=True),
        Binding("k", "kill_selected", "Kill selected", show=True),
    ]

    def __init__(self, interval: float = 2.0, animate: bool = True):
        super().__init__()
        self.interval = interval
        self.animate_brand = animate and not _env_flag("FANMON_NO_ANIM")
        self.engine = Engine()
        self._rows: dict[str, list] = {}   # table id -> [Rec | Proc] per row
        self._all_procs: list[Proc] = []   # last snapshot, for instant re-sort
        self._proc_sort = "cpu"
        self._fanless: bool | None = None
        self._boot_screen: BrandBoot | None = None
        self._boot_started = 0.0
        self._pending_snapshot: dict | None = None
        self._refresh_timer = None

    # -- compose ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid(id="stats"):
            with Vertical(classes="stat", id="fan-tile"):
                yield Label("FAN", classes="stat-title", id="fan-title")
                yield Label("—", id="fan-val")
                yield ProgressBar(id="fan-bar", total=100, show_eta=False,
                                  show_percentage=False)
                yield Label("", id="fan-detail", classes="stat-sub")
                yield Label("", id="fan-detail2", classes="stat-sub")
            with Vertical(classes="stat"):
                yield Label("TEMP", classes="stat-title")
                yield Label("—", id="temp-val")
                yield Label("", id="temp-detail", classes="stat-sub")
                yield Label("", id="temp-detail2", classes="stat-sub")
            with Vertical(classes="stat"):
                yield Label("CPU", classes="stat-title")
                yield Label("—", id="cpu-val")
                yield Label("", id="cpu-cores", classes="stat-sub")
                yield Label("", id="cpu-detail", classes="stat-sub")
            with Vertical(classes="stat"):
                yield Label("MEMORY", classes="stat-title")
                yield Label("—", id="mem-val")
                yield ProgressBar(id="mem-bar", total=100, show_eta=False,
                                  show_percentage=False)
                yield Label("", id="mem-detail", classes="stat-sub")
                yield Label("", id="mem-detail2", classes="stat-sub")
        yield Static("sampling…", id="verdict")
        with TabbedContent(initial="tab-close", id="tabs"):
            with TabPane("Close", id="tab-close"):
                yield VerticalScroll(
                    Static("", id="advisories", classes="caption"),
                    DataTable(id="recs-table"),
                )
            with TabPane("CPU", id="tab-cpu"):
                yield Static("", id="cpu-summary", classes="caption")
                yield Static("", id="cpu-core-bars")
                yield Sparkline([], summary_function=max, id="cpu-spark")
                yield Static("", id="cpu-caption", classes="caption")
                yield DataTable(id="cpu-table")
            with TabPane("Memory", id="tab-mem"):
                yield Static("", id="mem-summary", classes="caption")
                yield Static("", id="mem-break")
                yield Sparkline([], summary_function=max, id="mem-spark")
                yield Static("", id="mem-caption", classes="caption")
                yield DataTable(id="mem-table")
            with TabPane("Processes", id="tab-procs"):
                yield Static("", id="procs-caption", classes="caption")
                yield DataTable(id="proc-table")
            with TabPane("Watchdog", id="tab-watchdog"):
                yield VerticalScroll(
                    Static("", id="wd-probe", classes="caption"),
                    DataTable(id="wd-table"),
                )
        yield Footer()

    # -- lifecycle ----------------------------------------------------------

    def on_mount(self) -> None:
        self.register_theme(brand.textual_theme())
        self.theme = "abc"
        self._setup_tables()
        if self.animate_brand:
            self._boot_screen = BrandBoot()
            self._boot_started = time.monotonic()
            self.push_screen(self._boot_screen)
        self._spawn_refresh(initial=True)

    def _schedule_boot_finish(self) -> None:
        remaining = max(0.0, _BOOT_MIN_SECONDS -
                        (time.monotonic() - self._boot_started))
        self.set_timer(remaining, self._finish_boot)

    def _finish_boot(self) -> None:
        if self._boot_screen is not None and self.screen is self._boot_screen:
            self.pop_screen()
        self._boot_screen = None
        self.call_later(self._show_initial_snapshot)

    def _show_initial_snapshot(self) -> None:
        if self._pending_snapshot is not None:
            self._apply_snapshot(self._pending_snapshot)
            self._pending_snapshot = None
        self._start_refresh_timer()

    def _start_refresh_timer(self) -> None:
        if self._refresh_timer is None:
            self._refresh_timer = self.set_interval(self.interval,
                                                    self._spawn_refresh)

    def _setup_tables(self) -> None:
        recs = self.query_one("#recs-table", DataTable)
        recs.cursor_type = "row"
        recs.add_columns("#", "process / group", "RSS", "CPU", "age", "why")

        for tid in ("#cpu-table", "#mem-table", "#proc-table"):
            t = self.query_one(tid, DataTable)
            t.cursor_type = "row"
            t.add_columns("PID", "process", "RSS", "CPU", "age", "cat")

        wd = self.query_one("#wd-table", DataTable)
        wd.cursor_type = "row"
        wd.add_columns("when", "state", "RPM", "attribution")

    # -- refresh worker -----------------------------------------------------

    def _spawn_refresh(self, initial: bool = False) -> None:
        sample = self._initial_sample if initial else self._sample
        self.run_worker(sample, exclusive=True, group="sample", thread=True)

    def _initial_sample(self) -> dict:
        self.engine.snapshot()
        return self.engine.snapshot()

    def _sample(self) -> dict:
        # Runs in a worker thread; blocking I/O lives here, not on the UI.
        return self.engine.snapshot()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group != "sample":
            return
        if event.state == WorkerState.SUCCESS:
            if self._boot_screen is not None:
                self._pending_snapshot = event.worker.result
                self._schedule_boot_finish()
            else:
                self._apply_snapshot(event.worker.result)
                self._start_refresh_timer()
        elif event.state == WorkerState.ERROR and self._refresh_timer is None:
            if self._boot_screen is not None:
                self._schedule_boot_finish()
            else:
                self._start_refresh_timer()

    # -- apply snapshot to widgets -----------------------------------------

    def _apply_snapshot(self, snap: dict) -> None:
        self._fanless = snap["fanless"]
        self._update_stats(snap)
        self._update_verdict(snap)
        self._update_recs(snap)
        self._all_procs = snap["procs"]
        self._update_cpu_tab(snap)
        self._update_mem_tab(snap)
        self._render_proc_table()
        self._update_watchdog(snap)
        self.sub_title = snap["header_sub"]

    def _update_stats(self, snap: dict) -> None:
        fan, temps, mem, cpu, therm = (snap["fan"], snap["temps"], snap["mem"],
                                       snap["cpu"], snap["thermal"])
        throttle = therm.throttle_pct
        tcolor = _throttle_color(throttle)
        speed = (Text(f"CPU speed {100 - throttle}%", style=tcolor) if therm.known
                 else Text("CPU speed —", style=brand.MUTED))

        # FAN tile becomes a COOLING tile on a fanless machine.
        if fan.fanless:
            self.query_one("#fan-title", Label).update("COOLING")
            self.query_one("#fan-val", Label).update(Text.assemble(
                ("passive ", "bold"), ("· no fan", brand.MUTED)))
            self.query_one("#fan-bar", ProgressBar).update(progress=throttle)
            self.query_one("#fan-detail", Label).update(speed)
            self.query_one("#fan-detail2", Label).update(Text(
                f"throttled {throttle}%" if throttle else "not throttled",
                style=tcolor))
        else:
            duty = int(fan.duty * 100)
            self.query_one("#fan-title", Label).update("FAN")
            self.query_one("#fan-val", Label).update(Text.assemble(
                (f"{fan.rpm:,.0f} ", "bold"), ("RPM ", brand.MUTED),
                (f"{duty}%", brand.heat_color(duty / 100))))
            self.query_one("#fan-bar", ProgressBar).update(progress=duty)
            if fan.present is None:
                self.query_one("#fan-detail", Label).update(
                    Text("no SMC reader", style=brand.MUTED))
                self.query_one("#fan-detail2", Label).update(
                    Text("install Stats.app", style=brand.MUTED))
            else:
                self.query_one("#fan-detail", Label).update(Text(
                    f"target {fan.target:,.0f} RPM", style=brand.MUTED))
                self.query_one("#fan-detail2", Label).update(speed)

        tv = self.query_one("#temp-val", Label)
        if temps and temps.hottest_c:
            tv.update(Text.assemble(
                (f"{temps.hottest_c:.0f}°C ",
                 f"bold {brand.heat_color((temps.hottest_c - 40) / 60)}"),
                (f" [{temps.hottest_key}]", brand.MUTED),
            ))
            bits = [f"{label} {c:.0f}°"
                    for key, (label, c) in temps.notable.items()
                    if key != temps.hottest_key][:4]
            self.query_one("#temp-detail", Label).update(
                Text(bits[0] if bits else "", style=brand.MUTED))
            self.query_one("#temp-detail2", Label).update(
                Text(bits[1] if len(bits) > 1 else "", style=brand.MUTED))
        else:
            tv.update("—")
            self.query_one("#temp-detail", Label).update(
                Text("no sensors", style=brand.MUTED))
            self.query_one("#temp-detail2", Label).update(
                Text("install Stats.app", style=brand.MUTED))

        l1, cores = snap["load1"], snap["cores"]
        if cpu.available:
            total = cpu.total_pct
            self.query_one("#cpu-val", Label).update(Text.assemble(
                (f"{total:.0f}% ", f"bold {brand.heat_color(total / 100)}"),
                (f"P {cpu.p_busy:.0f}%  E {cpu.e_busy:.0f}%" if cpu.e_cores
                 else f"{cpu.ncpu} cores", brand.MUTED),
            ))
            self.query_one("#cpu-cores", Label).update(_core_glyphs(cpu))
        else:
            self.query_one("#cpu-val", Label).update("—")
            self.query_one("#cpu-cores", Label).update("")
        self.query_one("#cpu-detail", Label).update(Text(
            f"load {l1:.1f} / {snap['load5']:.1f} / {snap['load15']:.1f}"
            f" · {cores}c", style=brand.MUTED))

        used_pct = int(mem["used_pct"])
        swap_pct = int(mem["swap_used_pct"])
        self.query_one("#mem-val", Label).update(Text.assemble(
            (f"{mem['used_gb']:.1f}", "bold"),
            (f"/{mem['total_gb']:.0f} GB ", brand.MUTED),
            (f"{used_pct}%", brand.heat_color(used_pct / 100)),
        ))
        self.query_one("#mem-bar", ProgressBar).update(progress=used_pct)
        self.query_one("#mem-detail", Label).update(Text.assemble(
            (f"swap {mem['swap_used_gb']:.1f}/{mem['swap_total_gb']:.0f} GB ",
             brand.MUTED),
            (f"{swap_pct}%", brand.heat_color(swap_pct / 100)),
        ))
        self.query_one("#mem-detail2", Label).update(Text(
            f"compressor x{mem['comp_ratio']:.1f}", style=brand.MUTED))

    def _update_verdict(self, snap: dict) -> None:
        v = snap["verdict"]
        color = brand.SEVERITY.get(v.severity, brand.MIST)
        icon = _KIND_ICON.get(v.kind, "•")
        box = self.query_one("#verdict", Static)
        box.remove_class("ok", "watch", "high")
        box.add_class(v.severity)
        t = Text()
        t.append(f"{icon}  ", style=color)
        t.append(v.headline, style=f"bold {color}")
        t.append("\n")
        t.append(v.detail, style=brand.MIST)
        box.update(t)

    def _update_recs(self, snap: dict) -> None:
        table = self.query_one("#recs-table", DataTable)
        table.clear()
        recs = snap["recs"]
        self._rows["recs-table"] = recs
        for i, r in enumerate(recs, 1):
            table.add_row(
                str(i),
                Text(r.label, style=_cat_style(r.category)),
                f"{r.rss_mb:,.0f}M",
                f"{r.cpu_pct:,.0f}%",
                f"{r.age_h:,.0f}h",
                Text(r.reason, style=brand.MUTED),
                key=str(i),
            )
        adv = snap.get("advisories") or []
        cap = self.query_one("#advisories", Static)
        if adv:
            lines = Text()
            lines.append("system daemons (not closeable):\n",
                         style=f"bold {brand.MUTED}")
            lines.append("  ".join(adv), style=brand.MUTED)
            cap.update(lines)
        elif not recs:
            cap.update(Text("nothing to close — system looks healthy",
                            style=brand.SAGE))
        else:
            cap.update(
                Text("ranked for the active regime · select a row, press [k] to "
                     "SIGTERM", style=brand.MUTED)
            )

    def _fill_proc_table(self, table_id: str, ranked: list[Proc]) -> None:
        table = self.query_one(f"#{table_id}", DataTable)
        table.clear()
        self._rows[table_id] = ranked
        for p in ranked:
            table.add_row(
                str(p.pid),
                Text(p.comm, style=_cat_style(p.category)),
                f"{p.rss_mb:,.0f}",
                f"{p.cpu_pct:,.0f}%",
                f"{p.age_h:,.0f}h",
                Text(p.category, style=brand.MUTED),
                key=str(p.pid),
            )

    def _update_cpu_tab(self, snap: dict) -> None:
        cpu, procs = snap["cpu"], snap["procs"]
        summary = self.query_one("#cpu-summary", Static)
        if cpu.available:
            summary.update(Text.assemble(
                (f"{cpu.total_pct:.0f}% busy ",
                 f"bold {brand.heat_color(cpu.total_pct / 100)}"),
                (f"across {cpu.ncpu} cores  ·  user {cpu.user_pct:.0f}%  "
                 f"sys {cpu.sys_pct:.0f}%", brand.MUTED),
                ("  ·  P = performance, E = efficiency" if cpu.e_cores else "",
                 brand.MUTED),
            ))
            self.query_one("#cpu-core-bars", Static).update(_core_bars(cpu))
        else:
            summary.update(Text("per-core data unavailable on this system",
                                style=brand.MUTED))
            self.query_one("#cpu-core-bars", Static).update("")
        self.query_one("#cpu-spark", Sparkline).data = snap["cpu_hist"] or [0]
        self.query_one("#cpu-caption", Static).update(Text(
            f"total CPU over the last {len(snap['cpu_hist'])} samples ↑  ·  "
            f"top {_TOP_N_TAB} by CPU ↓  ·  [k] kills the selected PID",
            style=brand.MUTED))
        ranked = sorted(procs, key=lambda p: p.cpu_pct, reverse=True)[:_TOP_N_TAB]
        self._fill_proc_table("cpu-table", ranked)

    def _update_mem_tab(self, snap: dict) -> None:
        mem, procs = snap["mem"], snap["procs"]
        used_frac = mem["used_pct"] / 100.0
        self.query_one("#mem-summary", Static).update(Text.assemble(
            (f"{mem['used_gb']:.1f} of {mem['total_gb']:.0f} GB used ",
             f"bold {brand.heat_color(used_frac)}"),
            (f"·  memory free {mem['free_pct']}%" if mem.get("free_pct")
             is not None else "", brand.MUTED),
            (f"  ·  page in {mem['pagein_rate']:.0f}/s  out "
             f"{mem['pageout_rate']:.0f}/s", brand.MUTED),
        ))
        self.query_one("#mem-break", Static).update(_mem_breakdown(mem))
        self.query_one("#mem-spark", Sparkline).data = snap["mem_hist"] or [0]
        self.query_one("#mem-caption", Static).update(Text(
            f"RAM used over the last {len(snap['mem_hist'])} samples ↑  ·  "
            f"top {_TOP_N_TAB} by resident memory ↓  ·  [k] kills the "
            f"selected PID", style=brand.MUTED))
        ranked = sorted(procs, key=lambda p: p.rss_mb, reverse=True)[:_TOP_N_TAB]
        self._fill_proc_table("mem-table", ranked)

    def _render_proc_table(self) -> None:
        key = {"cpu": lambda p: p.cpu_pct,
               "mem": lambda p: p.rss_mb,
               "age": lambda p: p.age_s}[self._proc_sort]
        ranked = sorted(self._all_procs, key=key, reverse=True)[:_TOP_N_PROCS]
        self._fill_proc_table("proc-table", ranked)
        self.query_one("#procs-caption", Static).update(
            Text(f"top {len(ranked)} of {len(self._all_procs)} processes · "
                 f"sorted by {self._proc_sort} · [k] kills the selected PID",
                 style=brand.MUTED)
        )

    def _update_watchdog(self, snap: dict) -> None:
        wd = snap["watchdog"]
        state_style = {"OK": brand.SAGE, "WARN": brand.PEACH,
                       "CRIT": brand.CORAL}.get(wd.probe_state, brand.MUTED)
        self.query_one("#wd-probe", Static).update(Text.assemble(
            ("fan-activity ", brand.MUTED),
            (wd.probe_state, f"bold {state_style}"),
            (f"   ·   trigger ≥{wd.trigger_rpm} RPM   re-arm ≤{wd.reset_rpm} RPM",
             brand.MUTED),
        ))
        table = self.query_one("#wd-table", DataTable)
        table.clear()
        for e in wd.events:
            rpm_style = brand.CORAL if e.rpm >= wd.trigger_rpm else brand.MIST
            table.add_row(
                f"{e.day[5:]} {e.time}",
                Text(e.to_state, style=_state_style(e.to_state)),
                Text(f"{e.rpm}", style=rpm_style),
                Text(_attribution(e.detail), style=brand.MUTED),
                key=f"{e.day}{e.time}",
            )

    # -- actions ------------------------------------------------------------

    def action_refresh(self) -> None:
        self._spawn_refresh()

    def _step_tab(self, delta: int) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        cur = tabs.active if tabs.active in _TABS else _TABS[0]
        tabs.active = _TABS[(_TABS.index(cur) + delta) % len(_TABS)]

    def action_next_tab(self) -> None:
        self._step_tab(+1)

    def action_prev_tab(self) -> None:
        self._step_tab(-1)

    def action_sort_cpu(self) -> None:
        self._proc_sort = "cpu"
        self._render_proc_table()

    def action_sort_mem(self) -> None:
        self._proc_sort = "mem"
        self._render_proc_table()

    def action_sort_age(self) -> None:
        self._proc_sort = "age"
        self._render_proc_table()

    def action_kill_selected(self) -> None:
        target = self._kill_target()
        if target is None:
            self.notify("focus a process table first", severity="warning")
            return
        label, pids = target
        self.push_screen(ConfirmKill(label, pids), self._do_kill)

    def _kill_target(self):
        """(label, pids) for the row under the focused table's cursor."""
        focused = self.focused
        if not isinstance(focused, DataTable) or focused.id not in self._rows:
            return None
        rows = self._rows[focused.id]
        idx = focused.cursor_row
        if not (0 <= idx < len(rows)):
            return None
        r = rows[idx]
        if isinstance(r, Rec):
            return r.label, list(r.pids)
        return f"{r.comm} (PID {r.pid})", [r.pid]

    def _do_kill(self, confirmed: bool) -> None:
        if not confirmed:
            return
        target = self._kill_target()
        if target is None:
            return
        label, pids = target
        sent, missing = [], []
        for pid in pids:
            if not _pid_alive(pid):
                missing.append(pid)
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                sent.append(pid)
            except ProcessLookupError:
                missing.append(pid)
            except PermissionError:
                self.notify(f"no permission for PID {pid}", severity="error")
        note = f" → {len(missing)} already gone" if missing else ""
        self.notify(f"SIGTERM sent to {len(sent)} process(es) for {label}{note}",
                    severity="information")
        self._spawn_refresh()


# --- helpers --------------------------------------------------------------

def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _core_glyphs(cpu) -> Text:
    """One block glyph per core, coloured by heat: the CPU tile's mini chart."""
    t = Text(no_wrap=True)
    for pct, label in zip(cpu.per_core, cpu.labels):
        glyph = _SPARK[min(7, int(pct / 100 * 7.99))]
        t.append(glyph, style=brand.heat_color(pct / 100))
        if label.startswith("E") and cpu.e_cores and label == f"E{cpu.e_cores - 1}":
            t.append(" ")   # gap between the E and P clusters
    return t


def _core_bars(cpu, width: int = 14) -> Text:
    """Two columns of `label ████░░ 42%` bars, one row per pair of cores."""
    t = Text(no_wrap=True)
    cells = []
    for pct, label in zip(cpu.per_core, cpu.labels):
        cell = Text(no_wrap=True)
        cell.append(f"{label:>3} ", style=brand.MUTED)
        cell.append_text(brand.bar(pct / 100, width))
        cell.append(f" {pct:3.0f}%", style=brand.heat_color(pct / 100))
        cells.append(cell)
    for i in range(0, len(cells), 2):
        t.append_text(cells[i])
        if i + 1 < len(cells):
            t.append("    ")
            t.append_text(cells[i + 1])
        if i + 2 < len(cells):
            t.append("\n")
    return t


def _mem_breakdown(mem) -> Text:
    total = mem["total_gb"] or 1.0
    t = Text(no_wrap=True)
    rows = [
        ("app", mem["app_gb"], brand.SALMON, "memory apps are actively using"),
        ("wired", mem["wired_gb"], brand.PEACH, "kernel + drivers, can't be paged"),
        ("compressed", mem["comp_occupied_gb"], brand.CORAL,
         f"holding {mem['comp_stored_gb']:.1f} GB at x{mem['comp_ratio']:.1f}"),
        ("cached", mem["cached_gb"], brand.RUST, "file cache, freed on demand"),
    ]
    for i, (name, gb, color, note) in enumerate(rows):
        t.append(f"{name:>10} ", style=brand.MUTED)
        t.append_text(brand.bar(gb / total, 24, color=color))
        t.append(f" {gb:5.1f} GB  ", style="bold")
        t.append(note, style=brand.MUTED)
        t.append("\n")
    swap_frac = mem["swap_used_pct"] / 100.0
    t.append(f"{'swap':>10} ", style=brand.MUTED)
    t.append_text(brand.bar(swap_frac, 24))
    t.append(f" {mem['swap_used_gb']:5.1f} GB  ", style="bold")
    t.append(f"of {mem['swap_total_gb']:.0f} GB on disk · what makes a Mac feel slow",
             style=brand.MUTED)
    return t


def _throttle_color(throttle: int) -> str:
    """0 = sage, mild = peach, ≥30% held back = coral."""
    return brand.SAGE if throttle == 0 else (brand.PEACH if throttle < 30
                                             else brand.CORAL)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _attribution(detail: str) -> str:
    # Trim the duplicated "fan NNNN RPM;" prefix recorded in the event logs.
    if ";" in detail:
        return detail.split(";", 1)[-1].strip()[:80]
    return detail[:80]


def _cat_style(cat: str) -> str:
    return {"agent": brand.SALMON, "browser": brand.PEACH, "chat": "#C9A0DC",
            "app": brand.MIST, "system": brand.MUTED}.get(cat, brand.MIST)


def _state_style(state: str) -> str:
    return {"OK": brand.SAGE, "WARN": brand.PEACH,
            "CRIT": brand.CORAL}.get(state, brand.MUTED)


def run_app(interval: float, animate: bool = True) -> int:
    return FanMonitorApp(interval=interval, animate=animate).run()
