# User Guide

Everything `fm` shows you, and every key it responds to.

## Launch

```bash
fm                 # interactive TUI (default)
fm --interval 3    # refresh the live data every 3s (default 2.0)
fm --once          # print one snapshot frame and exit
```

## Screen anatomy

The TUI has four regions, top to bottom:

```
┌ Header ───────────────────────────────────────────────────────────────┐
┌ Stats row ────────────────────────────────────────────────────────────┐
│   FAN          TEMP          LOAD          MEMORY                      │
│   6097 RPM     88°C[TCMz]    15.6/10c      swap 98% · comp x6.5        │
│   ████████░░                ████░░░░       ██████████                   │
├ Verdict ──────────────────────────────────────────────────────────────┤
│  💾 Swap thrash — fan is spinning from memory pressure, not CPU        │
├ Tabs: [ Close ] [ Processes ] [ Watchdog ] ───────────────────────────┤
│  …the active tab's content…                                            │
└ Footer (key hints) ───────────────────────────────────────────────────┘
```

### The stats row

| Tile | Meaning |
|---|---|
| **FAN** | Actual fan RPM and % of its usable range (duty). The number that tells you *how* spun-up the fan is. |
| **TEMP** | The hottest sensor `fm` can see, with the sensor key, plus a few labelled readings (CPU complex, GPU, SSD). |
| **LOAD** | System load average (1/5/15 min) against the core count. Bar full at `load = 2 × cores`. |
| **MEMORY** | Swap used / total and %, plus the **memory-compressor ratio** (`comp xN` = how many GB of data are squeezed into 1 GB). |

### The Verdict

The most important line in the app. It names **why the fan is spinning**:

| Verdict | Colour | What it means |
|---|---|---|
| 💾 **Swap thrash** | red | Fan driven by memory pressure, *not* CPU. Close memory hogs. |
| 🔥 **CPU load** | yellow/red | Something is genuinely computing. The top contributor is named. |
| 🔀 **Memory + CPU** | red | Both are heating the machine. |
| 👀 **Fan elevated** | yellow | Fan is up but no single clear cause — possibly residual heat from a recent burst. |
| ✅ **Nominal** | green | Everything looks fine; no runaway CPU or thrash. |

Full detail on how that verdict is computed lives in [How It Works](how-it-works.md)
and [The Algorithm](algorithm.md).

## Tabs

### Close — "what should I shut down?"

The recommendation list, **ranked for the currently active regime**.

- Rows are ranked by a score that weights RAM, CPU and age according to whether
  you're in a memory or CPU regime.
- Grouped rows (e.g. `claude@session-476111c5 x3`) are *batches* — killing one
  terminates every process in the group.
- The caption above the table reminds you what `k` does.
- Below the Verdict, **system daemons** that happen to be hot (like WindowServer)
  are listed as *advisories*, never as kill targets.

### Processes — "what's actually using my Mac?"

One table of the top 80 processes, sorted by whichever metric you pick:

- `1` — sort by **CPU**
- `2` — sort by **memory** (RSS)
- `3` — sort by **age**

Columns: PID, process, RSS, CPU, age, category (the classification — `agent`,
`browser`, `chat`, `app`, `system`).

### Watchdog — "what has my own watchdog recorded?"

If you run the `dev.jensen.watchdog` service (or any watchdog that writes the
expected files), `fm` reads — never writes — its state: current probe status, the
configured trigger/re-arm RPM thresholds, and recent fan events. See
[Watchdog Integration](watchdog.md).

## Keys

| Key | Action | Notes |
|---|---|---|
| `q` | Quit | From anywhere. |
| `r` | Refresh now | Force an immediate re-sample. |
| `1` / `2` / `3` | Sort Processes by CPU / memory / age | |
| `k` | **Kill the selected row** | Opens a confirmation prompt. |
| `y` / `n` | Confirm / cancel the kill | Only when the prompt is up. |
| `tab` | Move focus | Between the Close / Processes tables. |

### Killing, safely

Pressing `k` on a row opens a prompt listing the exact PID(s):

```
┌ Terminate claude@session-476111c5 x3 ? ┐
│  SIGTERM → 3 process(es): 1234, 1235, 1236  │
│  [y] yes, terminate        [n] no           │
└───────────────────────────────────────────┘
```

Only after `y` does `fm` send `SIGTERM`, and it re-checks each PID is still alive
first. If a process already exited, `fm` reports it as "already gone." It never
sends `SIGKILL`.

!!! warning
    `fm` runs as your user, so it can only terminate processes you own. That's
    by design — it won't kill other users' or root's processes.

## Command-line flags

| Flag | Default | Meaning |
|---|---|---|
| `--interval <s>` | `2.0` | Live refresh interval. |
| `--once` | off | Print a single frame and exit. |
| `--warmup <s>` | `1.5` | For `--once`, the CPU-delta window before rendering. |
| `--help` | | Show usage. |

Next: understand the reasoning behind the verdict in
[How It Works](how-it-works.md).
