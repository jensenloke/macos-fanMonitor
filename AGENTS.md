# AGENTS.md — macOS Fan Monitor (`fm`)

A native macOS terminal app (Python + Textual) that answers "why is my Mac hot
— and what should I close?" with a deterministic verdict. An opt-in AI harness
gives an LLM second opinion.

## Run / test

```bash
fm                        # TUI (./fm launcher, or .venv/bin/python -m fanmon)
fm --once                 # one snapshot frame
make test                 # headless TUI smoke test (Textual run_test)
make test-unit            # stdlib unittest suite (tests/)
```

## AI harness — non-interactive setup/verify

```bash
fm ai providers                        # omp providers + Ollama/LM Studio
fm ai setup --from-omp dgx             # or --base-url … --model … --key-source …
fm ai status && fm ai test --tools     # verify
```

Config lives at `~/.config/macos-fanMonitor/config.toml`; `FANMON_AI_CONFIG`
overrides the path (use a `/tmp` path for tests — never touch a real config).

## Rules for agents

- The AI only **recommends** — every kill goes through the human-confirmed
  `k` → confirm → `SIGTERM` path. Never add auto-kill behaviour.
- **Never write an API key to config.toml** — `key_source` is a pointer:
  `omp:<name>` (key stays in `~/.omp/agent/models.yml`), `env:<VAR>`, or
  `none`. Never modify `~/.omp/agent/models.yml`.
- Never send `Proc.command` (full argv) to the provider — the packet carries
  `comm` + category only.
- No new runtime dependencies without asking; stdlib only for the AI layer.

See [docs/ai.md](docs/ai.md) for the full setup/privacy/tool reference.
