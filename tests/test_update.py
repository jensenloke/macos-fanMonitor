"""Tests for fanmon.update — all network/exec/pip paths monkeypatched."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fanmon import update
from fanmon.ai import config as ai_config


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["FANMON_UPDATE_CACHE"] = os.path.join(
            self._tmp.name, "update.json")
        os.environ["FANMON_AI_CONFIG"] = os.path.join(
            self._tmp.name, "config.toml")
        os.environ.pop("FANMON_NO_UPDATE", None)

    def tearDown(self):
        self._tmp.cleanup()
        for v in ("FANMON_UPDATE_CACHE", "FANMON_AI_CONFIG"):
            os.environ.pop(v, None)

    def test_is_newer(self):
        self.assertTrue(update.is_newer("0.3.2", "0.3.1"))
        self.assertTrue(update.is_newer("0.10.0", "0.9.9"))
        self.assertFalse(update.is_newer("0.3.1", "0.3.2"))
        self.assertFalse(update.is_newer("0.3.1", "0.3.1"))
        self.assertFalse(update.is_newer("0.3.2", "0.3.2-dev"))  # suffix ignored
        self.assertTrue(update.is_newer("0.3.2", "0.3.1-dev"))
        self.assertFalse(update.is_newer("", "0.1"))

    def test_detect_install_repo(self):
        repo = os.path.join(self._tmp.name, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        os.makedirs(os.path.join(repo, ".venv"))
        os.makedirs(os.path.join(repo, "fanmon"))
        fake = os.path.join(repo, "fanmon", "update.py")
        open(fake, "w").close()
        with patch.object(update, "__file__", fake):
            self.assertEqual(update.detect_install(), "repo")

    def test_cache_round_trip(self):
        self.assertIsNone(update.read_cache())
        update.write_cache("9.9.9")
        c = update.read_cache()
        self.assertEqual(c.latest, "9.9.9")
        self.assertGreater(c.checked_at, 0)
        update.mark_attempted()
        c = update.read_cache()
        self.assertEqual(c.latest, "9.9.9")
        self.assertEqual(c.attempted, "9.9.9")

    def _launch(self):
        calls = {"upgrade": [], "execv": [], "lines": []}
        with patch.object(update, "run_upgrade",
                          lambda m: calls["upgrade"].append(m) or (True, "")), \
             patch("os.execv",
                   lambda *a: calls["execv"].append(a)), \
             patch.object(update, "check_latest", lambda **k: "9.9.9"):
            update.launch_check(calls["lines"].append)
        return calls

    def test_launch_auto_updates_and_execs(self):
        update.write_cache("9.9.9")
        calls = self._launch()
        self.assertEqual(calls["upgrade"], ["repo"])
        self.assertEqual(len(calls["execv"]), 1)
        self.assertTrue(any("updating" in l for l in calls["lines"]))

    def test_launch_auto_off_does_not_upgrade(self):
        update.write_cache("9.9.9")
        cfg = ai_config.AiConfig()
        cfg.update.auto = False
        ai_config.save(cfg)
        calls = self._launch()
        self.assertEqual(calls["upgrade"], [])
        self.assertEqual(calls["execv"], [])

    def test_launch_no_update_env(self):
        update.write_cache("9.9.9")
        os.environ["FANMON_NO_UPDATE"] = "1"
        try:
            calls = self._launch()
        finally:
            del os.environ["FANMON_NO_UPDATE"]
        self.assertEqual(calls["upgrade"], [])
        self.assertEqual(calls["execv"], [])

    def test_launch_failure_continues(self):
        update.write_cache("9.9.9")
        calls = {"execv": [], "lines": []}
        with patch.object(update, "run_upgrade",
                          lambda m: (False, "boom")), \
             patch("os.execv", lambda *a: calls["execv"].append(a)):
            update.launch_check(calls["lines"].append)
        self.assertEqual(calls["execv"], [])
        self.assertTrue(any("failed" in l for l in calls["lines"]))

    def test_launch_skips_already_attempted(self):
        update.write_cache("9.9.9", attempted="9.9.9")
        calls = self._launch()
        self.assertEqual(calls["upgrade"], [])
        self.assertEqual(calls["execv"], [])

    def test_update_off_then_ai_status_not_configured(self):
        from fanmon import cli
        self.assertEqual(cli.main(["update", "--off"]), 0)
        self.assertFalse(ai_config.load().update.auto)
        self.assertEqual(cli.main(["ai", "status"]), 2)


if __name__ == "__main__":
    unittest.main()
