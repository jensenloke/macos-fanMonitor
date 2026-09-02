# The Algorithm

The precise decision logic and constants behind the Verdict and the Close list,
mirrored from `fanmon/regime.py`. These are the exact numbers in the code — where
a threshold lives is called out so you can tune it.

## Verdict: which regime?

Three boolean flags are computed from a snapshot, then combined.

### Signals

| Symbol | Source | 
|---|---|
| `cpu_busy` | sum of per-process CPU% (delta), i.e. % of **one** core |
| `cpu_frac` | `cpu_busy / (cores × 100)` — fraction of **all** cores |
| `swap_pct` | swap used / total × 100 |
| `comp_ratio` | compressor pages *stored* ÷ pages *occupied* |
| `free_pct` | system-wide RAM free % (`memory_pressure`) |
| `load1` | 1-minute load average |
| `fan_duty` | (rpm − min) ÷ (max − min), 0…1 |

### The three flags

```python
memory_pressure = swap_pct >= 70 or comp_ratio >= 4.0 or free_pct <= 10
cpu_pressure    = cpu_frac >= 0.55 or any(process.cpu_pct >= 90)
load_pressure   = load1 >= cores * 0.9
```

### The decision table

Evaluated top to bottom; the first match wins.

| # | Condition | Verdict | Kind | Severity |
|---|---|---|---|---|
| 1 | `memory_pressure and cpu_pressure` | Memory pressure + active CPU load | `mixed` | high |
| 2 | `memory_pressure and load_pressure and not cpu_pressure` | **Swap thrash** — fan from memory pressure | `memory` | high |
| 3 | `cpu_pressure` | CPU load — `<top>` biggest contributor | `cpu` | watch (<80%) / high |
| 4 | `fan_duty >= 0.4` | Fan elevated, no clear single cause | `watch` | watch |
| 5 | otherwise | Nominal | `healthy` | ok |

??? tip "Why the thresholds?"
    - **`swap_pct ≥ 70`** — past ~70% full, the swap file is contended and paging
      latency bites.
    - **`comp_ratio ≥ 4.0`** — if 4 GB of data compress into 1 GB, the compressor
      is absorbing enormous memory pressure. Values of 6–8× have been observed in
      real thrash episodes.
    - **`cpu_frac ≥ 0.55`** — over half of *all* cores busy is real compute, not
      noise. A single process at `≥ 90`% (≈ one core pinned) also trips it.
    - **`load1 ≥ 0.9 × cores`** — load near core-count means the run queue is
      saturated.

## Scoring the Close list

For each **group** (see grouping below), `fm` computes one score.

### Regime weights

| Regime | `w_rss` | `w_cpu` | `w_age` | Reason text |
|---|---|---|---|---|
| `memory` | 1.00 | 0.05 | 6.0 | frees RAM driving swap thrash |
| `cpu` | 0.02 | 1.00 | 1.0 | burning CPU now |
| `mixed` | 0.80 | 0.60 | 4.0 | contributing to memory + CPU load |
| `healthy`/`watch` | 0.50 | 0.30 | 2.0 | large / long-running |

### Category prior

| Category | Prior |
|---|---|
| `agent` | 1.00 |
| `browser` | 0.85 |
| `chat` | 0.60 |
| `app` | 0.50 |
| (unknown) | 0.40 |

### The formula

```python
rss      = sum(member.rss_mb)        # group resident memory
cpu      = sum(member.cpu_pct)       # group instantaneous CPU
age_h    = max(member.age_h)         # oldest member, in hours
score    = (rss*w_rss + cpu*w_cpu + age_h*w_age) * cat_prior
```

- `system`-category and non-closeable processes are **excluded entirely**.
- Groups with `score <= 0` are dropped.
- The list is sorted by score, descending, and **truncated to the top 6**.

### Worked example (memory regime)

A Chrome group with 2120 MB, 10% CPU, 190 h age:

```
score = (2120×1.0 + 10×0.05 + 190×6.0) × 0.85
      = (2120 + 0.5 + 1140) × 0.85
      = 3260 × 0.85
      ≈ 2771
```

Under a **CPU** regime the same group scores `(2120×0.02 + 10×1.0 + 190×1.0) × 0.85
≈ 175` — memory weight collapses because in a CPU regime RAM isn't the problem.
That flip is exactly the point.

## Grouping rule

```python
if category == "agent" and session_id:
    group = f"{comm}@{session_id}"   # swarm siblings collapse together
else:
    group = comm                      # otherwise group by process name
```

The `session_id` is the first `session-<8 hex>` token found in the command line.

## Tuning

All constants live at the top of `verdict()` / `recommend()` in
`fanmon/regime.py`. They're plain literals on purpose — adjust the flags to match
your machine's baseline (e.g. a 16 GB laptop will feel `memory_pressure` sooner
than a 32 GB desktop). If you find yourself tuning often, that's a good candidate
for a config file — see [Contributing](contributing.md).
