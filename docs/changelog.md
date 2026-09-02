# Changelog

All notable changes to `fm` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

_No pending changes._

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

[Unreleased]: https://github.com/jensenloke/macos-fanMonitor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jensenloke/macos-fanMonitor/releases/tag/v0.1.0
