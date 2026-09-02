# Getting Started

Get `fm` running on your Mac in under a minute.

## Requirements

| Requirement | Notes |
|---|---|
| **macOS** on Apple Silicon | Tested on an M4 MacBook Pro; the fanless layout is simulated with `FANMON_FANLESS=1`. Intel Macs are untested. |
| **Python 3.10+** | `python3 --version`. The app uses modern syntax (`X | None`). |
| **Stats.app** *(optional)* | A free menu-bar system monitor. `fm` reuses its read-only SMC helper to read fan RPM and temperatures — no extra drivers or `sudo`. Without it the FAN and TEMP tiles are blank; CPU, memory, throttle, processes and the verdict all work. |

!!! tip "MacBook Air owners"
    You have no fan, and `fm` knows: the FAN tile becomes **COOLING** and shows
    how much macOS is throttling the CPU. Head straight for the **CPU** and
    **Memory** tabs (`]` twice) — that's where an Air's heat shows up.

??? info "Why Stats.app?"
    Reading Apple-Silicon fan RPM and temperatures needs the **SMC**, which has
    no supported public API. Rather than bundle a signed driver, `fm` shells out
    to the SMC reader that ships with [Stats](https://github.com/exelban/stats):

    ```
    /Applications/Stats.app/Contents/Resources/smc
    ```

    This is the exact same helper the [watchdog](watchdog.md) uses, so no new
    privileged code enters the system. If you'd rather not install Stats, see
    [Troubleshooting](troubleshooting.md).

## Install

=== "Fresh clone"

    ```bash
    git clone https://github.com/jensenloke/macos-fanMonitor
    cd macOS-fanMonitor
    ./install.sh
    ```

=== "Already have the source"

    ```bash
    cd ~/Documents/tools/macOS-fanMonitor   # wherever you keep it
    ./install.sh
    ```

`install.sh` does three things:

1. Creates a private virtualenv at `.venv/` inside the project.
2. Installs `rich` and `textual` into it.
3. Symlinks the `fm` launcher into `~/.local/bin/`.

## First run

```bash
fm
```

The full-screen ABC mark assembles first while initial hardware sampling runs in
the background. It remains visible for at least three seconds, then opens the
live dashboard with its **Fan Monitor - Agentic Builders Collective** header and
**Verdict** banner. Press `q` to quit. Use `fm --no-anim` or
`FANMON_NO_ANIM=1` to skip the boot screen.

??? tip "Command not found?"
    If `fm` isn't found, `~/.local/bin` isn't on your `PATH`. Add it to your
    `~/.zshrc`:

    ```bash
    export PATH="$HOME/.local/bin:$PATH"
    ```

    Then open a new shell. The launcher follows its own symlink, so it works
    from any directory once it's on `PATH`.

## One-shot mode

For scripts, cron, or a quick non-interactive look, print a single frame and
exit:

```bash
fm --once
```

That renders the same information once and exits — handy for logging the state
at the moment a fan event fires.

## Verify your install

Two quick checks:

```bash
fm --once | head        # dashboard renders, fan/temp/swap lines present
./.venv/bin/python smoke_test.py   # headless TUI test → "SMOKE OK"
```

You're set. Next up: [User Guide](user-guide.md).
