# Watchdog Integration

`fm` can read from a companion **watchdog** service so the live dashboard lines up
with what has already been logged over time. This integration is **strictly
read-only**: `fm` never writes to, reconfigures, or restarts your watchdog.

## What it reads

It reads three files (paths relative to your home):

| File | Parsed for |
|---|---|
| `~/watchdogs/state/events/YYYY-MM-DD.log` | fan-activity events for today (+ yesterday) |
| `~/watchdogs/state/runner.log` | the latest `fan-activity` probe line → current OK / WARN / CRIT |
| `~/watchdogs/watchdogs.json` | the `fan_monitor` trigger / re-arm RPM thresholds |

The result appears on the **Watchdog** tab: current probe status, thresholds, and
recent events with their recorded top-CPU attribution.

```
fan-activity WARN   ·   trigger ≥3000 RPM   re-arm ≤2700 RPM
─────────────────────────────────────────────────────────────
when       state  RPM   attribution
09-01 22:43 WARN  3086  top CPU: TrashStorageExtension 140% …
09-01 11:28 WARN  3002  top CPU: WindowServer 89% …
08-31 23:45 WARN  3017  top CPU: WindowServer 79% …
```

## Expected event-log format

Each fan event is a single line like:

```
22:43 fan-activity OK -> WARN: fan 3086 RPM; top CPU: <proc> <n>% (PID <id>, <n> MB); …
```

`fm` also understands the recovery variants (`sensor recovered at N RPM`,
`re-armed at N RPM`). If your watchdog's format differs, the tab just shows fewer
events — nothing crashes.

## Reading the "top CPU" attribution with care

A watchdog that reports *"top CPU"* at the moment the fan rises **cannot see the
memory regime** — a thrashing process shows low CPU. So you may see events whose
attribution looks benign (WindowServer 89%, suggestd 108%) during what was really
a **swap-thrash** episode. This is the tool's central thesis in miniature:

!!! warning "Attribution blind spot"
    The watchdog answers *"what is computing right now"*. `fm` answers *"why is
    the fan spinning"*. When they disagree — high load, low attributed CPU, high
    swap — **trust the memory regime**. Use the Watchdog tab for *history*, and
    the live Verdict for *cause*.

## Optional: auto-open `fm` on a fan warning

You can have your watchdog pop `fm` in a new terminal the moment the fan crosses
its trigger. **This edits the watchdog itself** and is deliberately **not** done
for you. A safe pattern is to add a one-shot notification hook that launches:

```bash
open -a Terminal ~/.local/bin/fm    # or your terminal's CLI equivalent
```

Test it with a manually-triggered event before wiring it into the live service,
and keep it read-only apart from the launch.

## If you don't run a watchdog

The Watchdog tab simply reports "no fan events logged yet" and the rest of `fm`
is unaffected. Everything else reads directly from the OS, not from any watchdog.
