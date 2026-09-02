# Contributing

The full contributor guide lives in the documentation site:

**→ [Docs → Contributing](https://jensenloke.github.io/macos-fanMonitor/contributing/)**

Short version:

```bash
./install.sh            # venv + deps + symlink fm onto PATH
make run                # launch the TUI
make test               # headless smoke test
make docs               # preview the docs site
```

Please read the **non-negotiables** in the guide (read-only to hardware,
confirmed `SIGTERM`-only kills, system daemons never killable) before opening a
PR. Issues and ideas are welcome — check the
[Roadmap](https://jensenloke.github.io/macos-fanMonitor/roadmap/) first.
