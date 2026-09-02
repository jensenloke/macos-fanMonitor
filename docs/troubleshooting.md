# Troubleshooting

Quick fixes for the things most likely to go wrong.

## `fm: command not found`

`~/.local/bin` isn't on your `PATH`. Add it and reload:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Then `command -v fm` should print `/Users/jensen/.local/bin/fm` (your home).

## `venv missing. Run: …/install.sh`

The launcher follows its own symlink to find the project, but the `.venv/` wasn't
created. Re-run the installer from the **project** directory:

```bash
cd <project-dir>
./install.sh
```

## Fan / temperature readouts are missing (Temps empty)

`fm` reads the SMC through Stats.app. Check the helper exists and works:

```bash
/Applications/Stats.app/Contents/Resources/smc fans
```

If that errors or Stats isn't installed, install [Stats](https://github.com/exelban/stats).
Without it, fan/temp tiles show `—`; every other feature (verdict from load/swap,
processes, kill) still works.

??? tip "Not into Stats.app?"
    Point `SMC` in `fanmon/smc.py` at any CLI that prints `fans` / `list -t` in
    the same format. The rest of the app is independent of which binary you use.

## The screen looks garbled or won't redraw

Textual wants a real terminal (TTY). It won't render when piped/redirected —
that's expected, not a bug. For non-interactive output use:

```bash
fm --once
```

If a live session leaves the terminal messed up after a crash, run `reset`.

## First frame shows CPU / I/O as zero

The very first sample has no previous sample to diff against, so CPU% and page
I/O read `0` for one frame, then become real. `--once` handles this with a short
`--warmup` window before rendering.

## "nothing selected" when I press `k`

`k` acts on the focused table. Focus the **Close** or **Processes** table first
(`tab` moves focus), move the cursor onto a row, then press `k`.

## I killed something by accident

`fm` only sends `SIGTERM` and only after you confirm with `y`. Most apps quit
gracefully on `SIGTERM`. If a GUI app you killed had unsaved work, relaunch it —
`fm` never sends `SIGKILL` and never force-quits.

## `fm --once` prints fan 2500 RPM but the fan is clearly loud

Two possibilities:

1. **Genuinely calm now.** Fan events are bursts; the thrash may have passed
   between the event and your check. The Verdict reflects the *instant* you run
   it. Cross-check the **Watchdog** tab for recent events.
2. **You're seeing a *different* Mac.** `fm` reads the local machine. If you run
   it over SSH on a server, that host has no SMC fan — the tile will be empty.

## Load is high but the verdict says "Nominal"

That means load is high but memory and CPU are both relaxed — often transient
background work (Spotlight indexing, Time Machine, a media-analysis burst). The
**Processes** tab sorted by CPU (`1`) shows what; system daemons appear as
advisories. These usually self-resolve in minutes.

## Something still feels slow after closing the top recommendation

The top recommendation is a *heuristic*, not ground truth. Sort by **memory**
(`2`) and look at total RSS across all your long-running agent sessions — many
medium-sized processes can outweigh one big one. Closing a batched group (a
`… xN` row) frees all its members at once.

## Still stuck?

Run the headless test — if it fails, the environment is the issue, not your usage:

```bash
./.venv/bin/python smoke_test.py    # expect "SMOKE OK"
```

Open an issue with the output on the [GitHub
tracker](https://github.com/jensenloke/macos-fanMonitor/issues).
