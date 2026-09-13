"""Unit tests for the AI harness — stdlib unittest, no pytest."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from fanmon.ai import config as ai_config
from fanmon.ai.agent import Agent, parse_answer, Diagnosis
from fanmon.ai.context import build_packet, closeable_pids, groups
from fanmon.ai.tools import ToolContext, run_tool
from fanmon.ai.triggers import TriggerMonitor
from fanmon.procs import Proc


def _proc(pid, comm, ppid=1, cat="app", closeable=True, rss=100.0,
          cpu=5.0, group=None):
    return Proc(pid=pid, ppid=ppid, comm=comm, command=f"/bin/{comm}",
                rss_mb=rss, age_s=3600, cpu_pct=cpu, category=cat,
                closeable=closeable, group=group or comm)


def _snap(fan_duty=0.5, severity="ok", throttle=0, mem_used=50, swap=10,
          procs=None, fanless=False):
    procs = procs if procs is not None else [
        _proc(101, "chrome", cat="browser", group="Google Chrome"),
        _proc(102, "chrome", cat="browser", group="Google Chrome"),
        _proc(103, "kernel_task", cat="system", closeable=False),
    ]
    return {
        "fan": SimpleNamespace(fanless=fanless, rpm=4000, duty=fan_duty,
                               target=4500, present=True),
        "temps": SimpleNamespace(hottest_c=72.0, hottest_key="TC0P",
                                 notable={"TC0P": ("CPU", 72.0)}),
        "mem": {"used_pct": mem_used, "used_gb": 8.0, "total_gb": 16.0,
                "swap_used_pct": swap, "swap_used_gb": 1.0,
                "swap_total_gb": 2.0, "comp_ratio": 2.0,
                "pagein_rate": 5.0, "pageout_rate": 2.0},
        "cpu": SimpleNamespace(available=True, total_pct=40.0, p_busy=60.0,
                               e_busy=20.0),
        "thermal": SimpleNamespace(throttle_pct=throttle),
        "fanless": fanless,
        "load1": 3.0, "load5": 2.5, "load15": 2.0, "cores": 8,
        "verdict": SimpleNamespace(kind="cpu", headline="h", detail="d",
                                   severity=severity),
        "recs": [], "advisories": [],
        "watchdog": SimpleNamespace(probe_state="OK", trigger_rpm=3000,
                                    events=[]),
        "cpu_hist": [10, 20, 30], "mem_hist": [50, 55, 60],
        "heat_hist": [40, 50, 45],
        "procs": procs,
    }


class TestConfig(unittest.TestCase):
    def test_toml_round_trip(self):
        cfg = ai_config.AiConfig(base_url="https://x.test/v1",
                                 model="m-1", key_source="omp:dgx",
                                 cooldown_s=123)
        cfg.triggers.fan_duty_pct = 55
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "config.toml")
            ai_config.save(cfg, path)
            back = ai_config.load(path)
        self.assertEqual(back.base_url, cfg.base_url)
        self.assertEqual(back.model, "m-1")
        self.assertEqual(back.key_source, "omp:dgx")
        self.assertEqual(back.cooldown_s, 123)
        self.assertEqual(back.triggers.fan_duty_pct, 55)
        self.assertTrue(back.enabled)

    def test_load_missing_returns_none(self):
        self.assertIsNone(ai_config.load("/nonexistent/fm-ai.toml"))

    def test_omp_models_parse(self):
        fixture = (
            "providers:\n"
            "  dgx:\n"
            "    baseUrl: https://spark.test:8446/v1\n"
            "    apiKey: faketestkey123\n"
            "    api: openai-completions\n"
            "    models:\n"
            "    - id: dgx-current\n"
            "      name: DGX\n"
            "    - id: dgx-glm\n"
            "  other:\n"
            "    baseUrl: https://o.test/v1\n"
            "    apiKey: otherkey\n"
            "    models:\n"
            "    - id: m2\n"
        )
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "models.yml")
            with open(path, "w") as f:
                f.write(fixture)
            provs = ai_config.omp_providers(path)
            self.assertEqual(provs["dgx"]["base_url"],
                             "https://spark.test:8446/v1")
            self.assertEqual(provs["dgx"]["models"],
                             ["dgx-current", "dgx-glm"])
            self.assertNotIn("apiKey", provs["dgx"])
            old = ai_config.OMP_MODELS
            ai_config.OMP_MODELS = path
            try:
                self.assertEqual(ai_config.resolve_api_key("omp:dgx"),
                                 "faketestkey123")
            finally:
                ai_config.OMP_MODELS = old
        with self.assertRaises(KeyError):
            ai_config.resolve_api_key("env:FM_DEFINITELY_UNSET_VAR")


class TestPacket(unittest.TestCase):
    def test_no_command_anywhere_and_capped(self):
        procs = [_proc(1000 + i, f"p{i}") for i in range(30)]
        packet = build_packet(_snap(procs=procs))
        blob = json.dumps(packet)
        self.assertNotIn('"command"', blob)
        self.assertNotIn("/bin/p", blob)
        self.assertLessEqual(len(packet["top_cpu"]), 12)
        self.assertLessEqual(len(packet["top_rss"]), 12)
        for section in ("top_cpu", "top_rss"):
            for row in packet[section]:
                self.assertIn("comm", row)
                self.assertNotIn("command", row)
        self.assertEqual(packet["trends"]["cpu"]["last"], 30)

    def test_closeable_and_groups(self):
        snap = _snap()
        self.assertEqual(closeable_pids(snap), {101, 102})
        g = groups(snap)
        self.assertEqual(sorted(g["Google Chrome"]), [101, 102])
        self.assertIn("Google Chrome x2", g)


class TestTriggers(unittest.TestCase):
    def test_fire_once_cooldown_rearm(self):
        cfg = ai_config.AiConfig()
        cfg.cooldown_s = 0
        mon = TriggerMonitor(cfg)
        self.assertEqual(mon.update(_snap(fan_duty=0.8)),
                         "fan duty 80% >= 70%")
        self.assertIsNone(mon.update(_snap(fan_duty=0.9)))
        self.assertIsNone(mon.update(_snap(fan_duty=0.65)))  # still warm
        self.assertIsNone(mon.update(_snap(fan_duty=0.5)))   # re-arms <59.5%
        self.assertEqual(mon.update(_snap(fan_duty=0.75)),
                         "fan duty 75% >= 70%")

    def test_high_severity_streak(self):
        cfg = ai_config.AiConfig()
        cfg.cooldown_s = 0
        cfg.triggers.high_severity_samples = 3
        mon = TriggerMonitor(cfg)
        self.assertIsNone(mon.update(_snap(fan_duty=0.1, severity="high")))
        self.assertIsNone(mon.update(_snap(fan_duty=0.1, severity="high")))
        self.assertIn("severity", mon.update(
            _snap(fan_duty=0.1, severity="high")))
        self.assertIsNone(mon.update(_snap(fan_duty=0.1, severity="high")))
        self.assertIsNone(mon.update(_snap(fan_duty=0.1, severity="ok")))
        # streak resets; needs 3 consecutive highs again
        mon.update(_snap(fan_duty=0.1, severity="high"))
        self.assertIsNone(mon.update(_snap(fan_duty=0.1, severity="high")))
        self.assertIn("severity", mon.update(
            _snap(fan_duty=0.1, severity="high")))


class TestAgent(unittest.TestCase):
    def test_parse_answer_fences_and_prose(self):
        self.assertEqual(parse_answer('Sure! ```json\n{"diagnosis": "x"}\n```'),
                         {"diagnosis": "x"})
        self.assertEqual(parse_answer('{"a": 1} trailing'), {"a": 1})
        self.assertEqual(parse_answer("no json here"), {})

    def test_close_validation_and_group_expand(self):
        snap = _snap()
        ctx = ToolContext(engine=None, snap=snap)
        agent = Agent(provider=None, cfg=ai_config.AiConfig())
        answer = json.dumps({
            "diagnosis": "too hot",
            "confidence": 0.8,
            "actions": [
                {"type": "close", "target": "kernel_task", "pids": [103],
                 "why": "system pid must drop"},
                {"type": "close", "target": "Google Chrome x2", "pids": [],
                 "why": "browser hog"},
                {"type": "wait", "target": "", "pids": [], "why": "cool down"},
            ],
            "follow_up_questions": ["q1"],
        })
        d = agent._finish(answer, ctx)
        self.assertEqual(d.text, "too hot")
        close = [a for a in d.actions if a.type == "close"]
        self.assertEqual(len(close), 1)
        self.assertEqual(sorted(close[0].pids), [101, 102])
        self.assertTrue(any("kernel_task" in n for n in d.dropped))
        self.assertEqual(d.follow_ups, ["q1"])

    def test_tool_loop_with_fake_provider(self):
        calls = [{"id": "c1", "function": {
            "name": "process_tree", "arguments": '{"pid": 101}'}}]
        replies = iter([
            {"role": "assistant", "content": "", "tool_calls": calls},
            {"role": "assistant",
             "content": '{"diagnosis": "ok", "confidence": 0.5,'
                        ' "actions": [], "follow_up_questions": []}'},
        ])
        seen = []

        class FakeProvider:
            def chat(self, messages, tools):
                seen.append(list(messages))
                return next(replies)

        snap = _snap()
        ctx = ToolContext(engine=None, snap=snap)
        hist = []
        d = Agent(FakeProvider(), ai_config.AiConfig()).diagnose(
            build_packet(snap), ctx, "why?", hist)
        self.assertIsNone(d.error)
        self.assertEqual(d.text, "ok")
        self.assertEqual(d.tool_calls_made, ["process_tree"])
        tool_msgs = [m for m in seen[-1] if m.get("role") == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertEqual(tool_msgs[0]["tool_call_id"], "c1")
        self.assertEqual(len(hist), 2)
        # The assistant message sent back to the provider is stripped to the
        # OpenAI shape (no reasoning_content / provider fields).
        asst = [m for m in seen[-1] if m.get("role") == "assistant"
                and m.get("tool_calls")]
        self.assertEqual(asst[0]["tool_calls"], calls)
        self.assertEqual(set(asst[0]), {"role", "content", "tool_calls"})

    def test_followup_history_has_no_packets(self):
        class FakeProvider:
            def chat(self, messages, tools):
                return {"role": "assistant", "content":
                        '{"diagnosis": "d", "confidence": 0.1,'
                        ' "actions": [], "follow_up_questions": []}'}

        snap = _snap()
        ctx = ToolContext(engine=None, snap=snap)
        agent = Agent(FakeProvider(), ai_config.AiConfig())
        hist = []
        agent.diagnose(build_packet(snap), ctx, "why hot?", hist)
        agent.diagnose(build_packet(snap), ctx,
                       "which of those would you close first?", hist)
        self.assertEqual(len(hist), 4)
        self.assertFalse(any("SNAPSHOT:" in m["content"] for m in hist))


if __name__ == "__main__":
    unittest.main()
