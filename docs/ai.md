# AI harness (opt-in)

`fm`'s verdict and close recommendations are fully deterministic and need no
LLM. The **AI harness** is an optional second opinion: an agent with a
read-only tool loop that diagnoses *why* the Mac is hot and recommends what to
close — on demand (`a`) and when thresholds fire.

**It never kills anything.** Close actions become rows in the AI tab; you
select one and confirm through the same `k` → confirm → `SIGTERM` path as the
deterministic recommendations.

## Setup

### 30-second path

Press **`A`** in the TUI. The wizard lists providers detected in
`~/.omp/agent/models.yml` (e.g. `dgx`), prefills the endpoint and first model,
and writes `~/.config/macos-fanMonitor/config.toml`.

### From the shell

`fm ai <cmd>` does everything without opening the TUI — handy on a fresh
install or when an agent is configuring it for you:

```bash
fm ai providers    # what's available: omp providers, Ollama, LM Studio
fm ai setup …      # writes config.toml (refuses to overwrite; --force to redo)
fm ai status       # parsed config + whether the key resolves (never prints it)
fm ai test         # one chat round-trip; --tools also verifies tool calling
fm ai disable|enable
```

Worked examples:

```bash
# OMP harness (key read from ~/.omp/agent/models.yml at runtime)
fm ai setup --from-omp dgx

# Ollama — model must support tool calling (e.g. qwen3, llama3.1)
fm ai setup --base-url http://localhost:11434/v1 \
            --model qwen3:8b --key-source none

# LM Studio (served model with tool support)
fm ai setup --base-url http://localhost:1234/v1 \
            --model your-model-id --key-source none

# OpenAI — key stays in your environment, never in the file
export OPENAI_API_KEY=…
fm ai setup --base-url https://api.openai.com/v1 \
            --model gpt-4o-mini --key-source env:OPENAI_API_KEY
```

Tuning goes on the same line:
`--fan-duty 70 --throttle 30 --mem 90 --swap 70 --high-samples 3
--cooldown 300 --max-tool-rounds 6`.

### Verify

```bash
fm ai status       # exit 0 when configured; shows thresholds, key state
fm ai test         # "OK · <model> · <latency>s"
fm ai test --tools # also proves tool-call round-trips work
fm --once --ai     # snapshot + AI diagnosis panel
```

### Setting up with an AI agent

An agent can configure this end-to-end from the shell. Copy-paste block:

```text
Set up the fm AI harness:
1. `fm ai providers` — pick a reachable provider.
2. `fm ai setup --from-omp <name>` if an omp provider exists, else
   `fm ai setup --base-url <url> --model <id> --key-source env:<VAR>`
   (or `--key-source none` for Ollama/LM Studio).
3. `fm ai status` then `fm ai test --tools` — both must exit 0.
RULES: never paste an API key into config.toml — use env:<VAR>; never use
--force on an existing config unless I asked; do not modify
~/.omp/agent/models.yml.
```

The config file itself:

```toml
[ai]
enabled = true
provider = "openai-compatible"
base_url = "https://…/v1"
model = "dgx-current"
key_source = "omp:dgx"        # omp:<name> | env:<VAR> | none (no key)
max_tool_rounds = 6
cooldown_s = 300

[triggers]
fan_duty_pct = 70
throttle_pct = 30
mem_used_pct = 90
swap_used_pct = 70
high_severity_samples = 3     # verdict severity "high" for N samples
```

The API key is **never stored** by `fm`: `key_source` is a pointer resolved at
runtime. `FANMON_AI_CONFIG=/path/to.toml` overrides the config path (used by
tests).

## Using it

| key / flag | action |
|---|---|
| `a` | consult the AI on the latest snapshot (opens the AI tab) |
| `A` | setup wizard |
| `enter` in the AI tab's input | ask a follow-up (keeps last 12 messages of context) |
| `enter` on a follow-up option | quick-reply: sends that question as a consult |
| `space` on a `close` row | toggle it for a batch kill (`✓`) |
| `enter` on a `close` row | same as `space` |
| `enter` on `investigate`/`wait` | sends a "look closer with your tools" consult |
| `k` on the actions table | kills toggled rows as one confirmed batch; without toggles, kills the highlighted row |
| `fm --once --ai` | snapshot + diagnosis panel, then exit |
| `fm --once --ai --ask "…"` | same, with your question |

After a kill that came from the AI tab, `fm` automatically re-consults a few
seconds later ("verifying…") so the AI can check whether its advice helped.

Triggers auto-start a consult when fan duty / throttle / memory / swap cross
their thresholds, or the verdict stays `high` for `high_severity_samples`
samples in a row. A fired rule cools down for `cooldown_s` **and** must drop
below 85% of its threshold before it can fire again.

## Tools the agent may call

All read-only, all capped:

| tool | what it does |
|---|---|
| `proc_detail` | `ps` row for one PID (argv truncated to 120 chars), `lsof` open-file count, children, category |
| `process_tree` | ancestors + direct children from the snapshot's ppids |
| `resample` | a fresh full snapshot packet |
| `recent_logs` | `log show --last Nm` (N ≤ 10) filtered by message text, ≤ 60 lines |
| `thermal_state` | raw `pmset -g therm` + `pmset -g batt` |
| `watchdog_events` | last 20 fan-activity events from the watchdog logs |

## Privacy — what is and isn't sent

**Sent**: machine facts (cores, RAM total, fanless), gauge values (fan RPM/duty,
throttle, temps, CPU/memory/swap, load), the verdict text, deterministic
recommendation rows, watchdog probe state and events, trend summaries, and the
top 12 processes by CPU and by RSS — each as `pid`, `comm`, `category`,
`closeable`, `rss_mb`, `cpu_pct`, `age_h`, `group`.

**Never sent**: full command lines / argv (`Proc.command` is excluded from the
packet; `proc_detail` truncates argv to a basename + 3 args, 120 chars),
usernames, paths beyond process basenames, file contents, and of course the
API key itself (sent only in the `Authorization` header to your configured
endpoint).

## Recommend-only guarantee

The response contract is a single JSON object with `diagnosis`, `confidence`,
`actions`, and `follow_up_questions`. Before an action reaches the table,
`fm` drops any `close` action whose pids are not closeable or are category
`system`, and records the drop. What survives is a row — the human still picks
it and confirms the kill.
