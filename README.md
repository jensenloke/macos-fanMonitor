# macOS Fan Monitor (`fm`)

> **Why is my fan spinning — and what should I close?**
> An interactive terminal app that answers that at a glance, without asking an LLM.

A lazygit / yazi-style **Textual** TUI. Runs natively on macOS — **not Docker**
(see below for why Docker can't work here).

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

## Install

```bash
cd ~/Documents/tools/macOS-fanMonitor
./install.sh          # makes .venv, installs rich+textual, links fm into ~/.local/bin
```

Make sure `~/.local/bin` is on your `PATH`.

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
confirm prompt — killing stays a deliberate action, never automatic.

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

## Layout

```
macOS-fanMonitor/
  fm                # launcher -> .venv/bin/python -m fanmon
  install.sh        # venv + deps + PATH link
  requirements.txt  # rich, textual
  smoke_test.py     # headless TUI test (python smoke_test.py)
  README.md
  fanmon/
    __main__.py     # python -m fanmon
    cli.py          # entry: default = TUI, --once = snapshot
    app.py          # Textual App: gauges, tabs, kill, sort
    fanmon.tcss     # Textual stylesheet
    engine.py       # shared sampler (snapshot dict)
    smc.py          # fan + temperature sensors
    procs.py        # process snapshot + CPU delta + classification
    memory.py       # swap / compressor / pressure / load / uptime
    regime.py       # verdict + recommendation algorithm
    watchdog.py     # read-only watchdog log/config parsing
    render.py       # rich layout used by --once
```

## Tests

```bash
./.venv/bin/python smoke_test.py
```

Runs the app headless via Textual's `run_test()`: asserts the Close / Processes /
Watchdog tables populate, the `1/2/3` sort keys change the sort, and `k` opens
the confirm modal from both tables (and declines cleanly).

## Roadmap / ideas

- **Auto-open `fm` on a fan WARN** from the watchdog (needs a `watchdog-run` hook).
- Persist a **fan-RPM + temp sparkline** for an in-session trend.
- **Per-process swapped/compressed footprint** (macOS doesn't expose it cheaply).
