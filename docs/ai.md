# AI harness (opt-in)

`fm`'s verdict and close recommendations are fully deterministic and need no
LLM. The **AI harness** is an optional second opinion: an agent with a
read-only tool loop that diagnoses *why* the Mac is hot and recommends what to
close — on demand (`a`) and when thresholds fire.

**It never kills anything.** Close actions become rows in the AI tab; you
select one and confirm through the same `k` → confirm → `SIGTERM` path as the
deterministic recommendations.

## Setup

Press **`A`** in the TUI. The wizard lists providers detected in
`~/.omp/agent/models.yml` (e.g. `dgx`), prefills the endpoint and first model,
and writes `~/.config/macos-fanMonitor/config.toml`:

```toml
[ai]
enabled = true
provider = "openai-compatible"
base_url = "https://…/v1"
model = "dgx-current"
key_source = "omp:dgx"        # omp:<name> reads models.yml; env:<VAR> an env var
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
