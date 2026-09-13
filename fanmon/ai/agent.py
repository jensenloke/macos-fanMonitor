"""The consult loop: packet + question -> tool calls -> JSON diagnosis."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .prompts import SYSTEM_PROMPT
from .context import closeable_pids, groups
from .tools import TOOL_SCHEMAS, ToolContext, run_tool

_HISTORY_CAP = 12


@dataclass
class AiAction:
    type: str            # close | wait | investigate | advisory
    label: str
    pids: list = field(default_factory=list)
    why: str = ""


@dataclass
class Diagnosis:
    text: str = ""
    confidence: float = 0.0
    trigger: str = ""
    actions: list = field(default_factory=list)      # list[AiAction]
    follow_ups: list = field(default_factory=list)
    dropped: list = field(default_factory=list)      # notes on rejected actions
    tool_calls_made: list = field(default_factory=list)
    elapsed_s: float = 0.0
    error: str | None = None


def parse_answer(text: str) -> dict:
    """Extract the first {...} JSON block; tolerates ```json fences/prose."""
    if not text:
        return {}
    start = text.find("{")
    if start < 0:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj if isinstance(obj, dict) else {}
    except ValueError:
        return {}


class Agent:
    def __init__(self, provider, cfg):
        self.provider = provider
        self.cfg = cfg
        self.on_tool = None        # optional progress hook: fn(tool_name)

    def diagnose(self, packet: dict, tool_ctx: ToolContext,
                 question: str | None = None,
                 history: list | None = None) -> Diagnosis:
        t0 = time.monotonic()
        d = Diagnosis()
        history = history if history is not None else []
        ask = question or "Why is this Mac hot / fan spinning? What should I close?"
        user_msg = {"role": "user",
                    "content": f"SNAPSHOT:\n{json.dumps(packet, default=str)}\n\nQUESTION: {ask}"}
        messages = ([{"role": "system", "content": SYSTEM_PROMPT}]
                    + history[-_HISTORY_CAP:] + [user_msg])
        calls_made: list = []
        try:
            final = None
            for _ in range(max(1, self.cfg.max_tool_rounds)):
                msg = self.provider.chat(messages, TOOL_SCHEMAS)
                calls = msg.get("tool_calls") or []
                if not calls:
                    final = self._finish(msg.get("content") or "", tool_ctx)
                    break
                messages.append({
                    "role": "assistant",
                    "content": msg.get("content"),
                    "tool_calls": calls,
                })
                for c in calls:
                    fn = c.get("function", {})
                    name = fn.get("name", "?")
                    calls_made.append(name)
                    if self.on_tool:
                        self.on_tool(name)
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    res = run_tool(tool_ctx, name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": c.get("id", ""),
                        "content": json.dumps(res, default=str)[:8000],
                    })
            if final is None:
                final = Diagnosis(error="tool round limit reached")
            final.tool_calls_made = calls_made
            d = final
        except Exception as e:
            d.error = str(e) or type(e).__name__
            d.tool_calls_made = calls_made
        d.elapsed_s = round(time.monotonic() - t0, 1)
        history.append({"role": "user", "content": f"QUESTION: {ask}"})
        history.append({"role": "assistant",
                        "content": d.text or d.error or "(no answer)"})
        del history[:-_HISTORY_CAP]
        return d

    def _finish(self, content: str, tool_ctx: ToolContext) -> Diagnosis:
        d = Diagnosis()
        obj = parse_answer(content)
        if not obj:
            d.text = content.strip() or "(empty answer)"
            d.error = None if content.strip() else "no JSON in final answer"
            return d
        d.text = str(obj.get("diagnosis", "")).strip()
        try:
            d.confidence = float(obj.get("confidence", 0))
        except (TypeError, ValueError):
            d.confidence = 0.0
        d.follow_ups = [str(q) for q in obj.get("follow_up_questions") or []]
        ok_pids = closeable_pids(tool_ctx.snap)
        grp = groups(tool_ctx.snap)
        cat_by_pid = {p.pid: p.category for p in tool_ctx.snap["procs"]}
        for a in obj.get("actions") or []:
            if not isinstance(a, dict):
                continue
            atype = str(a.get("type", "advisory"))
            target = str(a.get("target", ""))
            pids = [int(p) for p in a.get("pids") or []
                    if isinstance(p, (int, float)) or str(p).isdigit()]
            why = str(a.get("why", ""))
            label = target or (f"pid {pids[0]}" if pids else atype)
            if atype != "close":
                d.actions.append(AiAction(atype, label, pids, why))
                continue
            if target in grp:
                pids = sorted(set(pids) | set(grp[target]))
            valid = [p for p in pids
                     if p in ok_pids and cat_by_pid.get(p) != "system"]
            if valid:
                d.actions.append(AiAction("close", label, valid, why))
            else:
                d.dropped.append(
                    f"close '{label}' dropped: no closeable pids")
        return d
