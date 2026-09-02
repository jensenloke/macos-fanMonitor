# Contributing

Thanks for wanting to make `fm` better. This guide gets you set up, explains the
layout, and covers the project's non-negotiables.

## Dev setup

```bash
git clone https://github.com/jensenloke/macos-fanMonitor
cd macOS-fanMonitor
./install.sh                 # creates .venv, installs rich + textual, links fm
source .venv/bin/activate    # optional, for running tools directly
```

Everything runs from the project's `.venv`. There's no global install.

## Project layout

```
fm                     launcher (resolves symlink, sets PYTHONPATH, runs app)
install.sh             venv + deps + ~/.local/bin symlink
requirements.txt       runtime deps (rich, textual)
requirements-docs.txt  docs deps (mkdocs-material)
smoke_test.py          headless TUI test
mkdocs.yml             docs site config
fanmon/
  __main__.py          python -m fanmon entry
  cli.py               arg parsing: default = TUI, --once = snapshot
  app.py               the Textual App: gauges, tabs, sort, kill
  fanmon.tcss          Textual stylesheet
  engine.py            sampler orchestration → one snapshot dict
  smc.py               fan + temperature sensors (Stats.app smc)
  procs.py             process snapshot, CPU-time delta, classification
  memory.py            swap / compressor / pressure / load / uptime
  regime.py            verdict + recommendation algorithm  ← the brain
  watchdog.py          read-only watchdog log/config parsing
  render.py            rich layout used by --once
docs/                  MkDocs Material site
```

## Run it while developing

```bash
./fm                       # live TUI
./fm --once                # single frame (great while iterating)
make run                   # same as ./fm
```

## Tests

```bash
make test                  # or: ./.venv/bin/python smoke_test.py
```

`smoke_test.py` drives the app headless via Textual's `run_test()`: it asserts the
Close / Processes / Watchdog tables populate, that the `1/2/3` sort keys change
the sort, and that `k` opens (and cleanly declines) the confirm modal from both
tables. When you add UI behaviour, **extend the smoke test to cover it** — the
headless pilot is the closest thing to a real terminal we have in CI.

## Documentation

```bash
make docs                  # local preview at http://127.0.0.1:8000
make docs-build            # strict build (what CI runs)
```

Docs live in `docs/`, configured by `mkdocs.yml`. A GitHub Actions workflow builds
and publishes to GitHub Pages on pushes to `main` that touch `docs/` or
`mkdocs.yml`. **`mkdocs build --strict` is the bar** — broken internal links fail
CI.

## Code style

- Keep it in the standard library + `rich`/`textual`; don't add heavy deps.
- Type hints throughout; `from __future__ import annotations` is the norm here.
- **Blocking I/O stays in the worker thread** (`_sample`) — never sample on the
  UI thread, or the app stalls.
- No new file unless the module has a clear single job.

## Non-negotiables (please don't undo these)

These come from the reason the tool exists:

1. **Read-only to hardware.** Only `smc fans` / `smc list -t`. No SMC writes.
2. **Killing is confirmed and `SIGTERM`-only.** Re-check liveness before sending.
   No `SIGKILL`, no automatic/background killing.
3. **System daemons are never killable.** They're symptoms; add them to
   advisories, not the kill list.
4. **Never invent a cause.** If the sample can't distinguish a legit build from a
   runaway, the Verdict should say so (`watch`), not guess.

## Proposing a change

For anything beyond a small fix, open an issue first — especially for items on
the [Roadmap](roadmap.md), so work isn't duplicated. For feature ideas, sketch
how it interacts with the safety model above.

## Committing

Conventional-ish messages (`Add …`, `Fix …`, `Tune …`) read well in this repo's
short history. Keep commits focused; a commit should leave `make test` green.

```bash
git add -A
git commit -m "Add per-process footprint column to the Processes tab"
git push
```

Open a pull request against `main`. CI builds the docs; the maintainer merges.
