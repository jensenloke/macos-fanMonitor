<p align="center">
  <a href="https://www.agenticbuilders.sg/"><img src="https://github.com/jensenloke/macos-fanMonitor/raw/main/docs/assets/abc-logo.png" width="420" alt="ABC — agentic builders collective"></a>
</p>

# macOS Fan Monitor (`fm`)

[![docs](https://github.com/jensenloke/macos-fanMonitor/actions/workflows/docs.yml/badge.svg)](https://github.com/jensenloke/macos-fanMonitor/actions/workflows/docs.yml)
[![PyPI](https://img.shields.io/pypi/v/macos-fanmon?color=F5A86B)](https://pypi.org/project/macos-fanmon/)
[![license: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://github.com/jensenloke/macos-fanMonitor/blob/main/LICENSE)
[![platform: macOS](https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)-black)](#requirements)
[![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/getting-started.md)
[![built for ABC](https://img.shields.io/badge/built%20for-agentic%20builders%20collective-E86F5E)](https://www.agenticbuilders.sg/)

📖 **Full documentation:** <https://jensenloke.github.io/macos-fanMonitor/>

> **Why is my Mac hot — and what should I close?**
> A terminal app that answers that at a glance, for MacBook Pros *and* fanless
> MacBook Airs, without asking an LLM.

Built for the members of the **[Agentic Builders Collective](https://www.agenticbuilders.sg/)**
(ABC) — a 1,000+ strong community of people who run AI agents on their Macs all
day and want to know what those agents are costing them in heat, CPU, and RAM.
`fm` wears the collective's colours: its peach → coral gradient *is* the heat
scale on every gauge. On launch, a full-screen ABC mark assembles slab by slab
while the first local signals are sampled. It remains visible for at least three
seconds, then gives way to the monitor; the header keeps the community identity
present as **Fan Monitor - Agentic Builders Collective**.

## Demo

<p align="center">
  <img src="https://github.com/jensenloke/macos-fanMonitor/raw/main/docs/assets/abc-fanmon-demo.gif" width="900" alt="Demo of the animated ABC boot screen and live fan, CPU, memory, process, and watchdog views">
</p>

The 20-second demo shows the ABC boot sequence, live gauges, and navigation
through the CPU, Processes, and Watchdog tabs.

---

## Contents

- [Demo](#demo)
- [What it shows](#what-it-shows)
- [MacBook Air (no fan)](#macbook-air-no-fan)
- [The core idea](#the-core-idea)
- [Install](#install)
- [Run & keys](#run)
- [Data sources](#data-sources-all-read-only)
- [Why not Docker](#why-a-native-cli-instead-of-docker)
- [Documentation](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/index.md) — getting started, user guide, algorithm, roadmap, and more
- [Contributing](https://github.com/jensenloke/macos-fanMonitor/blob/main/CONTRIBUTING.md)

## What it shows

Four live gauges, a one-line **Verdict** naming the cause, and five tabs:

| Tile | What it tells you |
|---|---|
| **FAN** / **COOLING** | Fan RPM and duty on machines with a fan. On a fanless Air the tile becomes **COOLING** and shows how much macOS is throttling the CPU (`pmset -g therm`). |
| **TEMP** | Hottest sensor plus CPU / GPU / SSD readings (via Stats.app's SMC helper). |
| **CPU** | Total busy %, P-core vs E-core split, and one block glyph per core. |
| **MEMORY** | RAM used of total, swap used, compressor ratio. |

| Tab | Question it answers |
|---|---|
| **Close** | *What should I shut down?* Ranked for the active regime, swarm sessions grouped. |
| **CPU** | *Which cores are pinned, and by what?* Per-core bars, a session sparkline, top 14 by CPU. |
| **Memory** | *Where did my RAM go?* App / wired / compressed / cached / swap breakdown, a sparkline, top 14 by RSS. |
| **Processes** | *Everything, sortable.* Top 80 by CPU / memory / age. |
| **Watchdog** | *What has my own watchdog recorded?* Read-only fan-event history. |

`k` on any table row terminates that process (or group) after a confirm prompt.

## MacBook Air (no fan)

An Air has no fan to spin, so the old question was meaningless there. `fm` now
detects the missing fan and switches its framing to **"why is my Mac hot?"**:

- The FAN tile becomes **COOLING** and reads the CPU speed limit from
  `pmset -g therm`. `CPU speed 72% · throttled 28%` is the Air's equivalent of a
  fan at full tilt.
- The Verdict gains a **🌡️ thermal** state: *"CPU throttled to 72% — passive
  cooling can't keep up."*
- The **CPU** and **Memory** tabs give Air users what they actually need: which
  cores are pinned, and whether an 8 / 16 GB machine is swapping.

<p align="center">
  <img src="https://github.com/jensenloke/macos-fanMonitor/raw/main/docs/assets/fm-air.png" width="900" alt="fm on a fanless Mac — COOLING tile and thermal verdict">
</p>

No Stats.app on the Air? The temperature tile goes blank; throttle, CPU, memory,
processes and the verdict all still work.

## The core idea

A hot Mac comes from **one of two very different causes**, and the fix for each
is different. The app decides which one is active, then ranks what to close
accordingly.

| Regime | Signal | What's really happening | Fix |
|---|---|---|---|
| **CPU** | load high **and** measured CPU% high | something is genuinely computing | close / wait on the CPU hog |
| **MEMORY** (swap thrash) | load high **but** measured CPU% **low** | system ran out of RAM and is paging; processes are **blocked on disk**, not computing | close **memory** hogs to stop the thrash |
| **THERMAL** | neither, but macOS is throttling | residual heat; passive cooling (Air) or fan can't shed it yet | let it cool, close the largest processes |

The memory regime is the sneaky one: `ps %cpu` and Activity Monitor's "top CPU"
both **miss it**, because thrashing processes show low CPU. That is the exact
failure mode from the real incidents that motivated this tool.

### The recommendation algorithm

1. **Classify** every process: `agent` (claude / codex / omp / devin / node_repl),
   `browser`, `chat`, `app`, or `system` (protected).
2. **Group** swarm siblings (all agents in one `session-…`) into one batch.
3. **Detect the regime** from swap %, compressor ratio, RAM-free %, load vs.
   core count, per-core busy %, and the pmset throttle level.
4. **Score** closeable processes with regime-appropriate weights (memory regime
   weights RAM + age; CPU regime weights CPU%), times a category prior.
5. **Never** recommend killing `system` daemons (WindowServer, Spotlight,
   `suggestd`, …) — those are symptoms; those get an *advisory* instead.

Full, exact thresholds and the scoring formula:
[docs → The Algorithm](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/algorithm.md).

## Requirements

- **macOS** on Apple Silicon (Intel untested; per-core labels fall back to `C0…`)
- **Python 3.10+**
- **[Stats.app](https://github.com/exelban/stats)** — *optional.* `fm` reuses its
  read-only SMC helper for fan RPM and temperatures. Without it those two tiles
  are blank; CPU, memory, throttle, processes and the verdict still work.

## Install

```bash
pipx install macos-fanmon     # one command; fm lands on your PATH
```

(No pipx? `brew install pipx`, or from a clone: `./install.sh` builds a venv
and links `fm` into `~/.local/bin` — make sure that is on your `PATH`.)

## Run

```bash
fm                    # interactive TUI
fm --once             # single snapshot frame, then exit (for scripts / quick look)
fm --interval 3       # live refresh every 3s
fm --no-anim          # skip the animated ABC boot screen
```

### Keys (TUI)

| key | action |
|---|---|
| `q` | quit |
| `r` | refresh now |
| `[` / `]` | previous / next tab |
| `1` / `2` / `3` | sort Processes by CPU / memory / age |
| `k` | **SIGTERM the selected row** (asks to confirm first) |
| `tab` | move focus between panes |

`k` re-checks each PID is still alive before sending `SIGTERM`, and shows a
confirm prompt — killing stays a deliberate action, never automatic. It only ever
sends `SIGTERM`, never `SIGKILL`.

## Data sources (all read-only)

| Data | Source |
|---|---|
| fan RPM / target / range, temps | `/Applications/Stats.app/Contents/Resources/smc` (optional) |
| CPU throttle (speed limit) | `pmset -g therm` |
| per-core busy % | Mach `host_processor_info` via ctypes (no sudo) |
| P / E core counts | `sysctl hw.perflevel0.logicalcpu`, `hw.perflevel1.logicalcpu` |
| process list, CPU-time delta, RSS, age | `ps -axww -o pid,ppid,rss,etime,time,command` |
| RAM total / app / wired / compressed / cached | `sysctl hw.memsize`, `vm_stat` |
| swap / pressure / page I/O | `sysctl vm.swapusage`, `vm_stat`, `memory_pressure` |
| load / cores / uptime | `sysctl vm.loadavg`, `hw.ncpu`, `kern.boottime` |
| fan events, probe state, thresholds | `~/watchdogs/state/events/*.log`, `runner.log`, `watchdogs.json` |

`fm` never writes to the SMC. Sampling runs in a background worker thread so the
UI never blocks.

## Why a native CLI instead of Docker

Docker Desktop on macOS runs containers inside a **Linux VM**. From inside a
container you **cannot** see the **SMC** (fan RPM, temps), the **macOS process
list**, `vm_stat` / `memory_pressure`, `pmset`, or the watchdog logs. Everything
this tool needs is host-side, so the correct architecture is a small native TUI
that reads them directly. Details:
[docs → How It Works](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/how-it-works.md#the-two-regimes).

## Watchdog integration

The **Watchdog** tab reads `dev.jensen.watchdog` state (read-only): current
`fan-activity` probe status (OK / WARN / CRIT), trigger / re-arm thresholds from
`watchdogs.json`, and recent fan events with their recorded attribution — so you
can correlate the live verdict against what the watchdog has been logging.
Details: [docs → Watchdog Integration](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/watchdog.md).

## Documentation

The full site is built from `docs/` and published to GitHub Pages. Browse
[online](https://jensenloke.github.io/macos-fanMonitor/) or preview locally:

```bash
make docs             # serve at http://127.0.0.1:8000
```

| Page | What's in it |
|---|---|
| [Getting Started](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/getting-started.md) | install & first run |
| [User Guide](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/user-guide.md) | every screen, tile, tab, and key |
| [How It Works](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/how-it-works.md) | the two-regime diagnosis logic |
| [The Algorithm](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/algorithm.md) | exact thresholds & scoring |
| [Watchdog Integration](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/watchdog.md) | correlating with your watchdog |
| [Troubleshooting](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/troubleshooting.md) | common issues, MacBook Air notes |
| [Roadmap](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/roadmap.md) | shipped / planned / won't-do |
| [Contributing](https://github.com/jensenloke/macos-fanMonitor/blob/main/CONTRIBUTING.md) | dev setup, tests, safety rules |
| [Changelog](https://github.com/jensenloke/macos-fanMonitor/blob/main/docs/changelog.md) | release history |

## Development

```bash
make test             # headless TUI smoke test (Textual run_test pilot), fan + fanless
make docs-build       # strict docs build (what CI runs)
```

`smoke_test.py` drives the app headless via Textual's `run_test()`, twice: once
as-is and once with `FANMON_FANLESS=1 FANMON_THROTTLE=72` to simulate a
throttling MacBook Air. It asserts the ABC boot remains visible for at least
three seconds, every table populates, `[` / `]` cycle the tabs, `1/2/3` change
the sort, and `k` opens the confirm modal from all four process tables.

Simulate an Air on any Mac:

```bash
FANMON_FANLESS=1 FANMON_THROTTLE=72 fm
```

## Layout

```
macOS-fanMonitor/
  pyproject.toml         # PyPI packaging: `fm` console script, package data
  fm                     # launcher -> .venv/bin/python -m fanmon (dev clone)
  Makefile               # run / once / test / docs / docs-build / clean
  install.sh             # venv + deps + PATH link (dev clone)
  scripts/verify-package.sh  # wheel build + clean-venv install rehearsal
  smoke_test.py          # headless TUI test (fan + fanless)
  mkdocs.yml             # docs site config
  docs/                  # documentation site (+ assets/: logo, screenshots)
  fanmon/
    __main__.py          # python -m fanmon
    cli.py               # entry: default = TUI, --once = snapshot
    app.py               # Textual App: ABC boot, gauges, tabs, kill, sort
    fanmon.tcss          # Textual stylesheet
    brand.py             # ABC palette, wordmark, Textual theme, heat scale
    engine.py            # shared sampler (snapshot dict + sparkline history)
    smc.py               # fan (+ fan-presence) and temperature sensors
    cpu.py               # per-core busy % via Mach host_processor_info
    thermal.py           # pmset -g therm throttle state
    procs.py             # process snapshot + CPU delta + classification
    memory.py            # RAM breakdown, swap, compressor, pressure, load, uptime
    regime.py            # verdict + recommendation algorithm
    watchdog.py          # read-only watchdog log/config parsing
    render.py            # rich layout used by --once
```

## About the Agentic Builders Collective

[ABC](https://www.agenticbuilders.sg/) is a Singapore-based community of 1,000+
builders shipping agentic software. `fm` started as one member's fix for a
MacBook that kept taking off during multi-agent sessions, and grew CPU and
memory views after Air owners pointed out they had no fan to monitor. Issues and
pull requests from members (and everyone else) are welcome.

## License

MIT — see [LICENSE](https://github.com/jensenloke/macos-fanMonitor/blob/main/LICENSE).
