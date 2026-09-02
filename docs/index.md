# macOS Fan Monitor

???+ tip inline "The one-line summary"

    **Why is my Mac fan spinning — and what should I close?** A native macOS
    terminal app that answers that at a glance, without asking an LLM each time.

`fm` is a lazygit / yazi-style **Textual** TUI. It watches your Mac's real
signals — fan RPM, temperatures, load, swap, and the live process list — figures
out **why** the fan is spinning, ranks the processes worth closing, and lets you
terminate one with a single key.

```
┌ macOS Fan Monitor ────────────────────────── 23:30 · up 18d · 1126 procs ┐
│ FAN 6097 RPM ████████░░ 93%   TEMP 88°C[TCMz] LOAD 15.6/10c  MEM swap 98%│
├ Verdict — why is the fan spinning? ──────────────────────────────────────┤
│ 💾 Swap thrash — fan is spinning from memory pressure, not CPU           │
│    load 15.6 on 10 cores but only 12% of a core busy; procs blocked on   │
│    disk, not computing. Close memory hogs below.                         │
├ [ Close ] [ Processes ] [ Watchdog ] ────────────────────────────────────┤
│  #  process / group              RSS     CPU  age  why                   │
│  1  claude@session-476111c5 x3  1626M   20%  24h  frees RAM thrash       │
│  2  Google x57                  2120M   10% 190h  frees RAM thrash       │
└──────────────────────────────────────────────────────────────────────────┘
```

## The core idea

A spinning fan on a Mac comes from **two very different causes**, and the fix for
each is different:

| Regime | Signal | What's happening | Fix |
|---|---|---|---|
| **CPU** | load high **and** CPU% high | something is genuinely computing | close / wait on the CPU hog |
| **Memory** (swap thrash) | load high **but** CPU% **low** | RAM is exhausted; processes are blocked on disk, not computing | close **memory** hogs |

The memory regime is the sneaky one — `ps %cpu` and Activity Monitor's "top CPU"
both **miss it**, because a process stuck paging shows *low* CPU. `fm` infers it
from the combination of swap pressure, the memory compressor, load, and how much
CPU is actually being used. That inference is the heart of the tool.

## Get started

```bash
git clone https://github.com/jensenloke/macos-fanMonitor
cd macOS-fanMonitor
./install.sh
fm
```

See [Getting Started](getting-started.md) for the full walkthrough, and
[User Guide](user-guide.md) for every screen and key.

## Jump to

- [:material-rocket-launch: Getting Started](getting-started.md) — install & first run
- [:material-account-eye: User Guide](user-guide.md) — tabs, gauges, keys, killing
- [:material-brain: How It Works](how-it-works.md) — the diagnosis logic
- [:material-calculator: The Algorithm](algorithm.md) — scoring & thresholds (exact)
- [:material-shield-check: Watchdog Integration](watchdog.md) — correlate with your own watchdog
- [:material-wrench: Troubleshooting](troubleshooting.md) — common issues
- [:material-map: Roadmap](roadmap.md) — what's next
- [:material-language-markdown: Contributing](contributing.md) — dev setup & tests

## Safety model

- **Read-only by default.** `fm` reads the SMC, `ps`, `vm_stat`, and your
  watchdog logs. It never writes to hardware.
- **Nothing dies unless you say so.** The `k` key shows a confirmation prompt and
  re-checks each PID is still alive before sending `SIGTERM`. It is never
  automatic.
- **System daemons are never killable.** WindowServer, Spotlight, `suggestd`, and
  friends are *symptoms*, not causes — the tool explains them instead of offering
  to kill them.

## License

MIT — see [LICENSE](https://github.com/jensenloke/macos-fanMonitor/blob/main/LICENSE).
