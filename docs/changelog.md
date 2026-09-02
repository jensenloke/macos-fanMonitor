# Changelog

All notable changes to `fm` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

_No pending changes._

## [0.2.0] — 2026-09-02

Built for the [Agentic Builders Collective](https://www.agenticbuilders.sg/),
and for its MacBook Air owners, who pointed out they had no fan to monitor.

### Added

- **MacBook Air / fanless support** — `fm` detects a fanless machine from the
  SMC fan count, retitles the FAN tile to **COOLING**, and reads the CPU speed
  limit from `pmset -g therm`. Verdict language adapts to fanless hardware.
- **🌡️ Thermal verdict** — a new regime for "no single hog, but macOS is
  throttling the clock"; severity `watch` under 30% throttle, `high` above.
- **CPU tab** — per-core bars labelled P (performance) / E (efficiency) via Mach
  `host_processor_info`, user / system split, a session sparkline, and the top
  14 processes by real CPU delta. `k` works here.
- **Memory tab** — Activity-Monitor-style breakdown (app / wired / compressed /
  cached / swap), memory-free %, page-in/out rates, a session sparkline, and
  the top 14 by resident memory. `k` works here.
- **CPU tile** replaces the LOAD tile: total busy %, P vs E %, one glyph per
  core; load average moves to its detail line.
- **MEMORY tile** now leads with RAM used of total; swap and compressor ratio
  move to the detail lines.
- **`[` / `]`** cycle tabs.
- **Animated ABC boot screen** — the sliced wordmark assembles in the community's
  peach → coral palette while initial hardware sampling runs in the background.
  It remains visible for at least three seconds, then the persistent header reads
  **Fan Monitor - Agentic Builders Collective**. `--no-anim` or
  `FANMON_NO_ANIM=1` skips it.
- **`FANMON_FANLESS=1`** and **`FANMON_THROTTLE=<pct>`** environment hooks to
  simulate an Air on any Mac; the smoke test runs both modes.
- **`fm --once`** gains the wordmark header, CPU-cores and Memory panels.

### Changed

- **ABC branding** — the full sliced ABC wordmark owns the boot sequence, the
  community name remains in the header, the TUI ships an `abc` Textual theme,
  and the logo's peach → coral gradient is the heat scale on every gauge
  (sage = fine, peach = warm, coral = hot).
- Stats.app is now **optional**: without it the FAN and TEMP tiles say so, and
  everything else works.
- Verdict copy is hardware-aware ("fan is spinning" vs. "your Mac is hot").
- Kill handling is table-agnostic; the confirm modal is reachable from Close,
  CPU, Memory and Processes.

### Docs

- README, index and user guide rewritten around the ABC identity, the Air
  story, and the new tabs; the README embeds a 20-second animated demo and real
  TUI screenshots live under `docs/assets/`.

## [0.1.0] — 2026-09-02

First release.

### Added

- **Regime detection** — distinguishes a spinning fan caused by genuine **CPU**
  load from one caused by **memory/swap thrash** (high load, low CPU, processes
  blocked on disk). Also detects *mixed* and *nominal*.
- **Textual TUI** — live fan/temp/load/memory gauges, a colour-coded **Verdict**
  naming the cause, and **Close / Processes / Watchdog** tabs.
- **Recommendation engine** — ranks closeable processes with **regime-weighted**
  scoring (memory regime weights RAM + age; CPU regime weights CPU%), grouped by
  swarm session so multi-agent sets collapse to one row.
- **Process classification** — `agent` / `browser` / `chat` / `app` / `system`,
  with system daemons surfaced as **advisories**, never as kill targets.
- **Confirm-gated kill** — `k` prompts, re-checks PID liveness, and sends
  `SIGTERM` only (never `SIGKILL`, never automatic).
- **Real CPU-time delta** sampling instead of the stale `ps %cpu` lifetime average.
- **Watchdog integration** — read-only fan-event history, live probe status, and
  trigger/re-arm thresholds from the `dev.jensen.watchdog` files.
- **`fm --once`** non-interactive snapshot mode for scripts and quick looks.
- **Headless smoke test** (`smoke_test.py`) via Textual's `run_test()` pilot.
- **Documentation site** (MkDocs Material) published to GitHub Pages, plus this
  changelog and a MIT license.

### Design notes

- **Not a Docker app** — containers run in a Linux VM and cannot reach the macOS
  SMC (fan/temps), the host process list, or `vm_stat`. A native tool is the only
  correct way to see host fan causes.
- Fan/temp readings reuse **Stats.app's** read-only SMC helper, so no new
  privileged code is introduced.

[Unreleased]: https://github.com/jensenloke/macos-fanMonitor/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jensenloke/macos-fanMonitor/releases/tag/v0.2.0
[0.1.0]: https://github.com/jensenloke/macos-fanMonitor/releases/tag/v0.1.0
