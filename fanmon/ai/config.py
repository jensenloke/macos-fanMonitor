"""AI harness configuration.

Stored in ~/.config/macos-fanMonitor/config.toml (override with
FANMON_AI_CONFIG=<path>). Flat schema, two tables:

    [ai]        enabled, provider, base_url, model, key_source,
                max_tool_rounds, cooldown_s
    [triggers]  fan_duty_pct, throttle_pct, mem_used_pct, swap_used_pct,
                high_severity_samples

key_source never stores a key: "omp:<provider>" reads the key from
~/.omp/agent/models.yml at runtime; "env:<VAR>" reads an environment
variable.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field

ENV_PATH = "FANMON_AI_CONFIG"
OMP_MODELS = os.path.expanduser("~/.omp/agent/models.yml")


@dataclass
class TriggerConfig:
    fan_duty_pct: int = 70
    throttle_pct: int = 30
    mem_used_pct: int = 90
    swap_used_pct: int = 70
    high_severity_samples: int = 3


@dataclass
class AiConfig:
    enabled: bool = True
    provider: str = "openai-compatible"
    base_url: str = ""
    model: str = ""
    key_source: str = ""
    max_tool_rounds: int = 6
    cooldown_s: int = 300
    triggers: TriggerConfig = field(default_factory=TriggerConfig)

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.model
                    and self.key_source)


def default_path() -> str:
    return os.environ.get(ENV_PATH) or os.path.expanduser(
        "~/.config/macos-fanMonitor/config.toml")


def load(path: str | None = None) -> AiConfig | None:
    """Config from disk, or None when no file exists (AI stays off)."""
    path = path or default_path()
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    cfg = AiConfig()
    ai = raw.get("ai", {})
    for k in ("enabled", "provider", "base_url", "model", "key_source",
              "max_tool_rounds", "cooldown_s"):
        if k in ai:
            setattr(cfg, k, ai[k])
    trg = raw.get("triggers", {})
    for k in TriggerConfig.__dataclass_fields__:
        if k in trg:
            setattr(cfg.triggers, k, trg[k])
    return cfg


def _toml_val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_val(x) for x in v) + "]"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def save(cfg: AiConfig, path: str | None = None) -> str:
    """Minimal TOML writer for our flat schema. Returns the path written."""
    path = path or default_path()
    lines = ["[ai]"]
    for k in ("enabled", "provider", "base_url", "model", "key_source",
              "max_tool_rounds", "cooldown_s"):
        lines.append(f"{k} = {_toml_val(getattr(cfg, k))}")
    lines += ["", "[triggers]"]
    for k in TriggerConfig.__dataclass_fields__:
        lines.append(f"{k} = {_toml_val(getattr(cfg.triggers, k))}")
    lines.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


# --- ~/.omp/agent/models.yml ----------------------------------------------
# A tolerant line parser for the subset we need — no yaml dependency:
#   providers:
#     <name>:
#       baseUrl: <url>
#       apiKey: <key>
#       models:
#       - id: <model-id>

def omp_providers(path: str | None = None) -> dict:
    """{name: {"base_url": str, "models": [ids]}} — keys are never returned."""
    out: dict = {}
    cur = None
    try:
        with open(path or OMP_MODELS) as f:
            lines = f.read().splitlines()
    except Exception:
        return out
    in_providers = False
    for line in lines:
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if indent == 0:
            in_providers = text.startswith("providers:")
            cur = None
            continue
        if not in_providers:
            continue
        if indent == 2 and text.endswith(":"):
            cur = text[:-1]
            out[cur] = {"base_url": "", "models": []}
        elif cur and indent >= 4:
            if text.startswith("baseUrl:"):
                out[cur]["base_url"] = text.split(":", 1)[1].strip().strip('"')
            elif re.match(r"-\s*id:", text):
                out[cur]["models"].append(
                    text.split(":", 1)[1].strip().strip('"'))
    return {k: v for k, v in out.items() if v["base_url"]}


def resolve_api_key(key_source: str) -> str:
    """Resolve "omp:<provider>", "env:<VAR>" or "none" to a key."""
    if key_source == "none":
        return ""
    if key_source.startswith("env:"):
        var = key_source[4:]
        key = os.environ.get(var, "")
        if not key:
            raise KeyError(f"env var {var} is not set")
        return key
    if key_source.startswith("omp:"):
        name = key_source[4:]
        key = _omp_key(name)
        if not key:
            raise KeyError(f"no apiKey for omp provider '{name}'")
        return key
    raise KeyError("key_source must be omp:<provider>, env:<VAR> or none")


def _omp_key(provider: str, path: str | None = None) -> str:
    try:
        with open(path or OMP_MODELS) as f:
            lines = f.read().splitlines()
    except Exception:
        return ""
    cur = None
    for line in lines:
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if indent == 2 and text.endswith(":"):
            cur = text[:-1]
        elif cur == provider and indent >= 4 and text.startswith("apiKey:"):
            return text.split(":", 1)[1].strip().strip('"')
    return ""
