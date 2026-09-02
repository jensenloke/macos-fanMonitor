"""Textual TUI app — a lazygit/yazi-style terminal application.

Layout:
  ┌ header ──────────────────────────────────────────────┐
  │ fan gauge · temp · load · memory  (live gauges)      │
  ├ verdict ─────────────────────────────────────────────┤
  │ why is the fan spinning?  (+ system-daemon advisories)│
  ├ tabs ────────────────────────────────────────────────┤
  │ Close | Processes | Watchdog                         │
  ├ footer ──────────────────────────────────────────────┤
  └──────────────────────────────────────────────────────┘

Keys:
  q / ctrl+q  quit          r  refresh now
  1 / 2 / 3   sort processes by CPU / memory / age
  k           SIGTERM the selected row (confirm prompt)
  tab         move focus between panes
"""
from __future__ import annotations

import os
import signal

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable, Footer, Header, Label, ProgressBar, Static, TabbedContent, TabPane,
)
from textual.worker import Worker, WorkerState

from .engine import Engine
from .procs import Proc


_SEV_STYLE = {"ok": "green", "watch": "yellow", "high": "red"}
_KIND_ICON = {"memory": "💾", "cpu": "🔥", "mixed": "🔀", "watch": "👀",
              "healthy": "✅"}
_TOP_N_PROCS = 80


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
                    ("Terminate ", "bold yellow"),
                    (self.label, "bold"),
                    (" ?", "bold yellow"),
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
    TITLE = "macOS Fan Monitor"
    SUB_TITLE = "why is the fan spinning?"
    CSS_PATH = "fanmon.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("1", "sort_cpu", "Sort CPU", show=True),
        Binding("2", "sort_mem", "Sort Mem", show=True),
        Binding("3", "sort_age", "Sort Age", show=True),
        Binding("k", "kill_selected", "Kill selected", show=True),
    ]

    def __init__(self, interval: float = 2.0):
        super().__init__()
        self.interval = interval
        self.engine = Engine()
        self._recs: list = []            # parallel to recs-table rows
        self._all_procs: list[Proc] = []  # last snapshot, for instant re-sort
        self._proc_table: DataTable | None = None
        self._proc_sort = "cpu"

    # -- compose ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid(id="stats"):
            with Vertical(classes="stat"):
                yield Label("FAN", classes="stat-title")
                yield Label("—", id="fan-val")
                yield ProgressBar(id="fan-bar", total=100, show_eta=False)
            with Vertical(classes="stat"):
                yield Label("TEMP", classes="stat-title")
                yield Label("—", id="temp-val")
                yield Label("", id="temp-detail", classes="stat-sub")
            with Vertical(classes="stat"):
                yield Label("LOAD", classes="stat-title")
                yield Label("—", id="load-val")
                yield ProgressBar(id="load-bar", total=100, show_eta=False)
            with Vertical(classes="stat"):
                yield Label("MEMORY", classes="stat-title")
                yield Label("—", id="mem-val")
                yield ProgressBar(id="swap-bar", total=100, show_eta=False)
        yield Static("sampling…", id="verdict")
        with TabbedContent(initial="tab-close"):
            with TabPane("Close", id="tab-close"):
                yield VerticalScroll(
                    Static("", id="advisories"),
                    DataTable(id="recs-table"),
                )
            with TabPane("Processes", id="tab-procs"):
                yield Static("", id="procs-caption")
                yield DataTable(id="proc-table")
            with TabPane("Watchdog", id="tab-watchdog"):
                yield VerticalScroll(
                    Static("", id="wd-probe"),
                    DataTable(id="wd-table"),
                )
        yield Footer()

    # -- lifecycle ----------------------------------------------------------

    def on_mount(self) -> None:
        self._setup_tables()
        self.engine.snapshot()          # prime deltas before the first frame
        self._spawn_refresh()
        self.set_interval(self.interval, self._spawn_refresh)

    def _setup_tables(self) -> None:
        recs = self.query_one("#recs-table", DataTable)
        recs.cursor_type = "row"
        recs.add_columns("#", "process / group", "RSS", "CPU", "age", "why")

        self._proc_table = self.query_one("#proc-table", DataTable)
        self._proc_table.cursor_type = "row"
        self._proc_table.add_columns("PID", "process", "RSS", "CPU", "age", "cat")

        wd = self.query_one("#wd-table", DataTable)
        wd.cursor_type = "row"
        wd.add_columns("when", "state", "RPM", "attribution")

    # -- refresh worker -----------------------------------------------------

    def _spawn_refresh(self) -> None:
        self.run_worker(self._sample, exclusive=True, group="sample", thread=True)

    def _sample(self) -> dict:
        # Runs in a worker thread; blocking I/O lives here, not on the UI.
        return self.engine.snapshot()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group == "sample" and event.state == WorkerState.SUCCESS:
            self._apply_snapshot(event.worker.result)

    # -- apply snapshot to widgets -----------------------------------------

    def _apply_snapshot(self, snap: dict) -> None:
        self._update_stats(snap)
        self._update_verdict(snap)
        self._update_recs(snap)
        self._all_procs = snap["procs"]
        self._render_proc_table()
        self._update_watchdog(snap)
        self.sub_title = snap["header_sub"]

    def _update_stats(self, snap: dict) -> None:
        fan, temps, mem = snap["fan"], snap["temps"], snap["mem"]
        duty = int(fan.duty * 100) if fan else 0

        self.query_one("#fan-val", Label).update(
            Text.assemble(
                (f"{fan.rpm:,.0f} ", "bold"), ("RPM ", "dim"),
                (f"{duty}%", _duty_color(duty)),
            )
        )
        self.query_one("#fan-bar", ProgressBar).update(progress=duty)

        tv = self.query_one("#temp-val", Label)
        if temps and temps.hottest_c:
            tv.update(Text.assemble(
                (f"{temps.hottest_c:.0f}°C ", "bold red"),
                (f" [{temps.hottest_key}]", "dim"),
            ))
            bits = " · ".join(
                f"{label} {c:.0f}°"
                for key, (label, c) in list(temps.notable.items())[:3]
                if key != temps.hottest_key
            )
            self.query_one("#temp-detail", Label).update(bits)
        else:
            tv.update("—")

        l1, cores = snap["load1"], snap["cores"]
        self.query_one("#load-val", Label).update(
            Text.assemble(
                (f"{l1:.2f} ", "bold"),
                (f"/ {snap['load5']:.1f} / {snap['load15']:.1f} · {cores}c", "dim"),
            )
        )
        self.query_one("#load-bar", ProgressBar).update(
            progress=min(100, int(l1 / (cores or 1) * 50))  # full at load=2*cores
        )

        swap_pct = int(mem["swap_used_pct"])
        self.query_one("#mem-val", Label).update(
            Text.assemble(
                (f"swap {mem['swap_used_gb']:.0f}/{mem['swap_total_gb']:.0f}GB ",
                 "bold"),
                (f" {swap_pct}%", _swap_color(swap_pct)),
                (f" · comp x{mem['comp_ratio']:.1f}", "dim"),
            )
        )
        self.query_one("#swap-bar", ProgressBar).update(progress=swap_pct)

    def _update_verdict(self, snap: dict) -> None:
        v = snap["verdict"]
        style = _SEV_STYLE.get(v.severity, "white")
        icon = _KIND_ICON.get(v.kind, "•")
        box = self.query_one("#verdict", Static)
        box.remove_class("ok", "watch", "high")
        box.add_class(v.severity)
        t = Text()
        t.append(f"{icon}  ", style=style)
        t.append(v.headline, style=f"bold {style}")
        t.append("\n")
        t.append(v.detail, style="grey70")
        box.update(t)

    def _update_recs(self, snap: dict) -> None:
        table = self.query_one("#recs-table", DataTable)
        table.clear()
        self._recs = snap["recs"]
        for i, r in enumerate(self._recs, 1):
            table.add_row(
                str(i),
                Text(r.label, style=_cat_style(r.category)),
                f"{r.rss_mb:,.0f}M",
                f"{r.cpu_pct:,.0f}%",
                f"{r.age_h:,.0f}h",
                Text(r.reason, style="grey58"),
                key=str(i),
            )
        adv = snap.get("advisories") or []
        cap = self.query_one("#advisories", Static)
        if adv:
            lines = Text()
            lines.append("system daemons (not closeable):\n", style="bold grey62")
            lines.append("  ".join(adv), style="grey58")
            cap.update(lines)
        elif not self._recs:
            cap.update(Text("nothing to close — system looks healthy", style="green"))
        else:
            cap.update(
                Text("ranked for the active regime · select a row, press [k] to "
                     "SIGTERM", style="grey54")
            )

    def _render_proc_table(self) -> None:
        if self._proc_table is None:
            return
        table = self._proc_table
        table.clear()
        key = {"cpu": lambda p: p.cpu_pct,
               "mem": lambda p: p.rss_mb,
               "age": lambda p: p.age_s}[self._proc_sort]
        ranked = sorted(self._all_procs, key=key, reverse=True)[:_TOP_N_PROCS]
        self._proc_rows = ranked
        for p in ranked:
            table.add_row(
                str(p.pid),
                Text(p.comm, style=_cat_style(p.category)),
                f"{p.rss_mb:,.0f}",
                f"{p.cpu_pct:,.0f}%",
                f"{p.age_h:,.0f}h",
                Text(p.category, style="grey54"),
                key=str(p.pid),
            )
        self.query_one("#procs-caption", Static).update(
            Text(f"top {len(ranked)} of {len(self._all_procs)} processes · "
                 f"sorted by {self._proc_sort} · [k] kills the selected PID",
                 style="grey54")
        )

    def _update_watchdog(self, snap: dict) -> None:
        wd = snap["watchdog"]
        state_style = {"OK": "green", "WARN": "yellow", "CRIT": "red"}.get(
            wd.probe_state, "grey50")
        self.query_one("#wd-probe", Static).update(Text.assemble(
            ("fan-activity ", "grey62"),
            (wd.probe_state, f"bold {state_style}"),
            (f"   ·   trigger ≥{wd.trigger_rpm} RPM   re-arm ≤{wd.reset_rpm} RPM",
             "grey54"),
        ))
        table = self.query_one("#wd-table", DataTable)
        table.clear()
        for e in wd.events:
            rpm_style = "red" if e.rpm >= wd.trigger_rpm else "grey70"
            table.add_row(
                f"{e.day[5:]} {e.time}",
                Text(e.to_state, style=_state_style(e.to_state)),
                Text(f"{e.rpm}", style=rpm_style),
                Text(_attribution(e.detail), style="grey58"),
                key=f"{e.day}{e.time}",
            )

    # -- actions ------------------------------------------------------------

    def action_refresh(self) -> None:
        self._spawn_refresh()

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
            self.notify("focus the Close or Processes table first",
                        severity="warning")
            return
        label, pids = target
        self.push_screen(ConfirmKill(label, pids), self._do_kill)

    def _kill_target(self):
        """(label, pids) for the row under the focused table's cursor."""
        focused = self.focused
        if isinstance(focused, DataTable):
            if focused.id == "recs-table":
                idx = focused.cursor_row
                if 0 <= idx < len(self._recs):
                    r = self._recs[idx]
                    return r.label, list(r.pids)
            elif focused is self._proc_table:
                rows = getattr(self, "_proc_rows", [])
                idx = focused.cursor_row
                if 0 <= idx < len(rows):
                    p = rows[idx]
                    return f"{p.comm} (PID {p.pid})", [p.pid]
        return None

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


def _duty_color(duty: int) -> str:
    return "green" if duty < 40 else ("yellow" if duty < 75 else "red")


def _swap_color(pct: int) -> str:
    return "green" if pct < 50 else ("yellow" if pct < 80 else "red")


def _cat_style(cat: str) -> str:
    return {"agent": "magenta", "browser": "cyan", "chat": "blue",
            "app": "white", "system": "grey58"}.get(cat, "white")


def _state_style(state: str) -> str:
    return {"OK": "green", "WARN": "yellow", "CRIT": "red"}.get(state, "grey50")


def run_app(interval: float) -> int:
    return FanMonitorApp(interval=interval).run()
