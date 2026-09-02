# Roadmap

What's shipped, what's planned, and what's deliberately **not** planned.

## Status legend

- ✅ shipped
- 🚧 in progress
- 🔜 planned
- 💡 idea / not scheduled
- 🚫 won't do

## Shipped (v0.1)

| | Feature |
|---|---|
| ✅ | Native Textual TUI (lazygit-style) + `fm --once` snapshot mode |
| ✅ | Regime detection: **CPU** vs **memory/swap-thrash** vs mixed vs nominal |
| ✅ | Fan duty, hot-sensor temp, load-vs-cores, swap/compressor gauges |
| ✅ | Regime-weighted **Close** recommendations with swarm grouping |
| ✅ | Process classification (agent / browser / chat / app / system) |
| ✅ | Sortable process table (`1/2/3`), focus navigation (`tab`) |
| ✅ | Confirm-gated `SIGTERM` kill with PID re-check |
| ✅ | System-daemon **advisories** instead of kill buttons |
| ✅ | Read-only **watchdog** integration (events, probe, thresholds) |
| ✅ | Real CPU-time **delta** sampling (not stale `ps %cpu`) |
| ✅ | Background-worker sampling so the UI never blocks |
| ✅ | Headless `run_test` smoke test; GitHub Pages docs |

## Shipped (v0.2)

| | Feature |
|---|---|
| ✅ | **MacBook Air / fanless** support: COOLING tile, `pmset -g therm` throttle, 🌡️ thermal verdict |
| ✅ | **CPU tab**: per-core P / E bars, user / sys split, sparkline, top-14 by real CPU |
| ✅ | **Memory tab**: app / wired / compressed / cached / swap breakdown, page I/O, sparkline, top-14 by RSS |
| ✅ | In-session **sparklines** for CPU and RAM (was "trend line", planned) |
| ✅ | **ABC branding**: animated boot, community header, `abc` Textual theme, brand gradient as heat scale |
| ✅ | `[` / `]` tab cycling; `k` from every process table; Stats.app optional |

## Planned

### 🔜 Heat sparkline
CPU and RAM sparklines shipped in v0.2. Next: a third one for fan duty (or
throttle % on an Air) and the hottest sensor, so you can see whether you're
*heating up* or cooling down.

### 🔜 Auto-open `fm` on a fan warning
A hook the watchdog can call to pop `fm` in a new terminal the moment fan RPM
crosses its trigger. Requires a small, opt-in change to the watchdog's fan
monitor (launching a process), so it ships behind an explicit install step and a
manual test — never silently.

### 🔜 Configurable thresholds + profiles
Move the detection/weighting constants (see [The Algorithm](algorithm.md)) into an
optional `~/.config/macos-fanMonitor/config.toml`, with a couple of built-in
profiles (e.g. *16 GB laptop*, *32 GB desktop*) so tuning doesn't require editing
source.

### 🔜 Kill history + undo hint
Log what `fm` terminated in-session, and surface a "relaunch" hint for GUI apps
it SIGTERM'd.

## Ideas (not scheduled)

- 💡 **Per-process footprint** (real swapped/compressed bytes per PID, not just
  RSS) via `footprint`/`heap`-style sampling — richer memory-regime ranking, but
  macOS doesn't expose it cheaply.
- 💡 **Fan-target prediction** — correlate recent CPU/memory spikes with fan RPM
  to warn *before* the fan spins up.
- 💡 **Optional remote host** — SSH a *snapshot* collector to another Mac and view
  it here (fan/SMC stay local-only; this would be load/swap/processes only).
- 💡 **Battery tile** — `pmset -g batt` charge, power source and whether the
  charger is keeping up under load (Air owners asked).
- 💡 **Per-process energy impact** — `top -o power` style ranking, the closest
  thing macOS exposes to "who is heating my Air".
- 💡 **Threshold-aware notification** — post a macOS notification on regime change
  even while `fm` is closed (would need a lightweight resident mode).

## Won't do

| | Reason |
|---|---|
| 🚫 Docker / container deployment | Containers run in a Linux VM and cannot read the macOS SMC, host `ps`, or `vm_stat`. A native tool is the *only* correct architecture here. |
| 🚫 Bundling a signed SMC kernel driver | Too invasive. Reusing Stats.app's reader keeps the privilege surface identical to what you already run. |
| 🚫 Automatic / background killing | Killing stays a deliberate, confirmed human action. The tool recommends; you decide. |
| 🚫 Sending `SIGKILL` | Force-kills lose data and can corrupt app state. `SIGTERM` only. |
| 🚫 "Fix everything" automation (auto-quitting apps, killing WindowServer) | System daemons are symptoms; auto-remediation would hide the real causes this tool exists to reveal. |

## Contributing

Ideas, issues, and PRs are welcome — see [Contributing](contributing.md). If you
build a planned item, open an issue first so effort isn't duplicated.
