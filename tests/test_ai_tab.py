"""Headless tests for the AI tab interactions (Textual run_test, no network)."""
import asyncio
import os
import signal
import tempfile
import unittest
from unittest.mock import patch

from fanmon.ai import config as ai_config
from fanmon.ai.agent import AiAction, Diagnosis
from fanmon.app import BrandBoot, ConfirmKill, FanMonitorApp
from textual.widgets import OptionList

CANNED = Diagnosis(
    text="test diagnosis", confidence=0.9, elapsed_s=1.0,
    actions=[
        AiAction("wait", "let it cool", [], "cool first"),
        AiAction("close", "Chrome x2", [11, 12], "browser hog"),
        AiAction("close", "Codex x1", [21], "idle agent"),
        AiAction("investigate", "mds", [99], "check daemon"),
    ],
    follow_ups=["q one", "q two", "q three"])


def _plain(widget) -> str:
    r = widget.render()
    return getattr(r, "plain", str(r)).strip()


class AiTabTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        cfg = ai_config.AiConfig(base_url="https://fake.test/v1",
                                 model="fake", key_source="env:FM_TEST_KEY")
        ai_config.save(cfg, os.path.join(self._tmp.name, "config.toml"))
        os.environ["FANMON_AI_CONFIG"] = os.path.join(
            self._tmp.name, "config.toml")
        os.environ["FANMON_NO_ANIM"] = "1"

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("FANMON_AI_CONFIG", None)
        os.environ.pop("FANMON_NO_ANIM", None)

    def test_ai_tab_interactions(self):
        asyncio.run(self._run())

    async def _run(self):
        app = FanMonitorApp(interval=1.0)
        questions = []

        def fake_run(snap, question, trigger):
            questions.append(question)
            return CANNED

        async with app.run_test(size=(140, 44)) as pilot:
            async def wait_for(cond, timeout=15):
                for _ in range(int(timeout / 0.1)):
                    if cond():
                        return True
                    await pilot.pause(0.1)
                return False

            app._ai_run = fake_run
            self.assertTrue(await wait_for(
                lambda: not isinstance(app.screen, BrandBoot)
                and app._ai_snap is not None))

            table = app.query_one("#ai-actions")
            fu = app.query_one("#ai-followups", OptionList)

            app.query_one("#tabs").active = "tab-ai"
            await pilot.press("a")
            self.assertTrue(await wait_for(lambda: table.row_count >= 4))
            self.assertTrue(await wait_for(lambda: not app._ai_busy))
            self.assertEqual(table.row_count, 4)
            self.assertEqual(fu.option_count, 3)
            self.assertTrue(fu.display)
            self.assertIn("cool first", _plain(app.query_one("#ai-why")))

            # space on row 0 (wait) does not toggle
            table.focus()
            await pilot.pause(0.2)
            table.move_cursor(row=0)
            await pilot.press("space")
            await pilot.pause(0.2)
            self.assertEqual(app._ai_toggled, set())
            # toggle the two close rows
            table.move_cursor(row=1)
            await pilot.press("space")
            table.move_cursor(row=2)
            await pilot.press("space")
            await pilot.pause(0.2)
            self.assertEqual(app._ai_toggled, {1, 2})

            # k -> batch ConfirmKill with union of pids
            killed = []
            with patch("os.kill",
                       lambda pid, sig: killed.append((pid, sig))):
                await pilot.press("k")
                await pilot.pause(0.4)
                self.assertIsInstance(app.screen, ConfirmKill)
                self.assertTrue(app.screen.label.startswith("2 AI actions"))
                self.assertEqual(app.screen.pids, [11, 12, 21])
                await pilot.press("y")
                await pilot.pause(0.4)
            for pid in (11, 12, 21):
                self.assertIn((pid, signal.SIGTERM), killed)
            # the verify flag arms only after the 6s timer fires
            self.assertIsNone(app._ai_verify_pending)
            app._arm_verify("x", 2)
            self.assertTrue(await wait_for(
                lambda: any("did it help" in (q or "") for q in questions)))
            self.assertTrue(await wait_for(lambda: not app._ai_busy))

            # Enter on the investigate row starts an investigate consult
            table.focus()
            await pilot.pause(0.2)
            table.move_cursor(row=3)
            await pilot.press("enter")
            self.assertTrue(await wait_for(
                lambda: any((q or "").startswith("Investigate")
                            for q in questions)))
            self.assertTrue(await wait_for(lambda: not app._ai_busy))

            # selecting follow-up option 0 asks exactly that question
            fu.focus()
            await pilot.pause(0.2)
            await pilot.press("enter")
            self.assertTrue(await wait_for(
                lambda: "q one" in questions))


if __name__ == "__main__":
    unittest.main()
