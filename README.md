# macOS Fan Monitor (`fm`)

[![docs](https://github.com/jensenloke/macos-fanMonitor/actions/workflows/docs.yml/badge.svg)](https://github.com/jensenloke/macos-fanMonitor/actions/workflows/docs.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![platform: macOS](https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)-black)](#requirements)
[![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](docs/getting-started.md)
[![tui: textual](https://img.shields.io/badge/TUI-textual-8833ff)](https://textual.textualize.io/)

📖 **Full documentation:** <https://jensenloke.github.io/macos-fanMonitor/>

> **Why is my fan spinning — and what should I close?**
> An interactive terminal app that answers that at a glance, without asking an LLM.

A lazygit / yazi-style **Textual** TUI. Runs natively on macOS — **not Docker**
(see [why](docs/how-it-works.md#the-two-regimes) Docker can't work here).

```
┌ macOS Fan Monitor ────────────────────────── 23:30 · up 18d · 1126 procs ┐
│ FAN 6097 RPM ████████░░ 93%   TEMP 88°C[TCMz] LOAD 15.6/10c  MEM swap 98%│
├ Verdict — why is the fan spinning? ──────────────────────────────────────┤
│ 💾 Swap thrash — fan is spinning from memory pressure, not CPU           │
│    load 15.6 on 10 cores but only 12% of a core busy; procs blocked on   │
│    disk, not computing. Close memory hogs below.                          │
├ [ Close ] [ Processes ] [ Watchdog ] ────────────────────────────────────┤
│  #  process / group              RSS     CPU  age  why                    │
│  1  claude@session-476111c5 x3  1626M   20%  24h  frees RAM thrash        │
│  2  Google x57                  2120M   10% 190h  frees RAM thrash        │
│      ▲ select a row and press [k] to SIGTERM it                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Contents

- [Why not Docker](#why-a-native-cli-instead-of-docker)
- [The core idea](#the-core-idea)
- [Install](#install)
- [Run & keys](#run)
- [Data sources](#data-sources-all-read-only)
- [Documentation](docs/index.md) — getting started, user guide, algorithm, roadmap, and more
- [Contributing](CONTRIBUTING.md)

## Requirements

- **macOS** on Apple Silicon (Intel untested)
- **Python 3.10+**
- **[Stats.app](https://github.com/exelban/stats)** — `fm` reuses its read-only
  SMC helper to read fan RPM + temperatures, so no new privileged code. Without
  it, fan/temp tiles are blank but everything else works.

## Why a native CLI instead of Docker

Docker Desktop on macOS runs containers inside a **Linux VM**. From inside a
container you **cannot** see:

- the **SMC** (fan RPM, temps) — that's macOS IOKit, not exposed to the VM;
- the **macOS process list** (`ps` shows the VM's processes, not your apps);
- `vm_stat` / `sysctl vm.swapusage` / `memory_pressure` (macOS memory internals);
- the **watchdog** logs (they live on the macOS host).

Everything this tool needs is host-side, so the correct architecture is a small
native TUI that reads the SMC + `ps` + `vm_stat` + watchdog logs directly.

## The core idea

A spinning fan here comes from **one of two very different causes**, and the fix
for each is different. The app decides which one is active, then ranks what to
close accordingly.

| Regime | Signal | What's really happening | Fix |
|---|---|---|---|
| **CPU** | load high **and** measured CPU% high | something is genuinely computing | close / wait on the CPU hog |
| **MEMORY** (swap thrash) | load high **but** measured CPU% **low** | system ran out of RAM and is paging; processes are **blocked on disk**, not computing | close **memory** hogs to stop the thrash |

The memory regime is the sneaky one: `ps %cpu` and the watchdog's "top CPU"
attribution both **miss it**, because thrashing processes show low CPU. That is
the exact failure mode from the real incidents that motivated this tool.

### The recommendation algorithm

1. **Classify** every process: `agent` (claude / codex / omp / devin / node_repl),
   `browser`, `chat`, `app`, or `system` (protected).
2. **Group** swarm siblings (all agents in one `session-…`) into one batch.
3. **Detect the regime** from swap %, compressor ratio, RAM-free %, load vs.
   core count, and measured CPU%.
4. **Score** closeable processes with regime-appropriate weights (memory regime
   weights RAM + age; CPU regime weights CPU%), times a category prior.
5. **Never** recommend killing `system` daemons (WindowServer, Spotlight,
   `suggestd`, …) — those are symptoms; those get an *advisory* instead.

Full, exact thresholds and the scoring formula:
[docs → The Algorithm](docs/algorithm.md).

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
```

### Keys (TUI)

| key | action |
|---|---|
| `q` | quit |
| `r` | refresh now |
| `1` / `2` / `3` | sort Processes by CPU / memory / age |
| `k` | **SIGTERM the selected row** (asks to confirm first) |
| `tab` | move focus between the Close / Processes tables |

`k` re-checks each PID is still alive before sending `SIGTERM`, and shows a
confirm prompt — killing stays a deliberate action, never automatic. It only ever
sends `SIGTERM`, never `SIGKILL`.

## Data sources (all read-only)

| Data | Source |
|---|---|
| fan RPM / target / range, temps | `/Applications/Stats.app/Contents/Resources/smc` |
| process list, CPU-time delta, RSS, age | `ps -axww -o pid,ppid,rss,etime,time,command` |
| swap / compressor / free / page I/O | `sysctl vm.swapusage`, `vm_stat`, `memory_pressure` |
| load / cores / uptime | `sysctl vm.loadavg`, `hw.ncpu`, `kern.boottime` |
| fan events, probe state, thresholds | `~/watchdogs/state/events/*.log`, `runner.log`, `watchdogs.json` |

`fm` never writes to the SMC. Sampling runs in a background worker thread so the
UI never blocks.

## Watchdog integration

The **Watchdog** tab reads `dev.jensen.watchdog` state (read-only): current
`fan-activity` probe status (OK / WARN / CRIT), trigger / re-arm thresholds from
`watchdogs.json`, and recent fan events with their recorded attribution — so you
can correlate the live verdict against what the watchdog has been logging.
Details: [docs → Watchdog Integration](docs/watchdog.md).

## Documentation

The full site is built from `docs/` and published to GitHub Pages. Browse
[online](https://jensenloke.github.io/macos-fanMonitor/) or preview locally:

```bash
make docs             # serve at http://127.0.0.1:8000
```

| Page | What's in it |
|---|---|
| [Getting Started](docs/getting-started.md) | install & first run |
| [User Guide](docs/user-guide.md) | every screen, tile, and key |
| [How It Works](docs/how-it-works.md) | the two-regime diagnosis logic |
| [The Algorithm](docs/algorithm.md) | exact thresholds & scoring |
| [Watchdog Integration](docs/watchdog.md) | correlating with your watchdog |
| [Troubleshooting](docs/troubleshooting.md) | common issues |
| [Roadmap](docs/roadmap.md) | shipped / planned / won't-do |
| [Contributing](CONTRIBUTING.md) | dev setup, tests, safety rules |
| [Changelog](docs/changelog.md) | release history |

## Development

```bash
make test             # headless TUI smoke test (Textual run_test pilot)
make docs-build       # strict docs build (what CI runs)
```

`smoke_test.py` drives the app headless via Textual's `run_test()`: it asserts the
Close / Processes / Watchdog tables populate, the `1/2/3` sort keys change the
sort, and `k` opens the confirm modal from both tables (and declines cleanly).

## Layout

```
macOS-fanMonitor/
  pyproject.toml         # PyPI packaging: `fm` console script, package data
  fm                     # launcher -> .venv/bin/python -m fanmon (dev clone)
  Makefile               # run / once / test / docs / docs-build / clean
  install.sh             # venv + deps + PATH link (dev clone)
  scripts/verify-package.sh  # wheel build + clean-venv install rehearsal
  requirements.txt       # rich, textual (dev clone)
  requirements-docs.txt  # mkdocs-material
  smoke_test.py          # headless TUI test
  mkdocs.yml             # docs site config
  docs/                  # documentation site
  fanmon/
    __main__.py          # python -m fanmon
    cli.py               # entry: default = TUI, --once = snapshot
    app.py               # Textual App: gauges, tabs, kill, sort
    fanmon.tcss          # Textual stylesheet
    engine.py            # shared sampler (snapshot dict)
    smc.py               # fan + temperature sensors
    procs.py             # process snapshot + CPU delta + classification
    memory.py            # swap / compressor / pressure / load / uptime
    regime.py            # verdict + recommendation algorithm
    watchdog.py          # read-only watchdog log/config parsing
    render.py            # rich layout used by --once
```

## License

MIT — see [LICENSE](LICENSE).
