"""In-process tests for `fm ai …` subcommands — no network."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fanmon import cli
from fanmon.ai import config as ai_config


class CliAiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "config.toml")
        os.environ["FANMON_AI_CONFIG"] = self.path

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("FANMON_AI_CONFIG", None)

    def test_setup_status_disable(self):
        rc = cli.main(["ai", "setup", "--base-url", "https://x.test/v1",
                       "--model", "m-1", "--key-source", "none",
                       "--fan-duty", "65"])
        self.assertEqual(rc, 0)
        cfg = ai_config.load(self.path)
        self.assertEqual(cfg.base_url, "https://x.test/v1")
        self.assertEqual(cfg.model, "m-1")
        self.assertEqual(cfg.key_source, "none")
        self.assertEqual(cfg.triggers.fan_duty_pct, 65)
        self.assertTrue(cfg.enabled)

        # second setup without --force refuses and leaves the file unchanged
        before = open(self.path).read()
        rc = cli.main(["ai", "setup", "--base-url", "https://other.test"])
        self.assertEqual(rc, 2)
        self.assertEqual(open(self.path).read(), before)

        # key_source "none" resolves to "" and status exits 0
        self.assertEqual(ai_config.resolve_api_key("none"), "")
        self.assertEqual(cli.main(["ai", "status"]), 0)

        # disable / enable flip [ai].enabled
        self.assertEqual(cli.main(["ai", "disable"]), 0)
        self.assertFalse(ai_config.load(self.path).enabled)
        self.assertEqual(cli.main(["ai", "enable"]), 0)
        self.assertTrue(ai_config.load(self.path).enabled)

    def test_status_missing_file(self):
        self.assertEqual(cli.main(["ai", "status"]), 2)

    def test_missing_key_reported(self):
        cli.main(["ai", "setup", "--base-url", "https://x.test/v1",
                  "--model", "m", "--key-source",
                  "env:FM_CLI_UNSET_TEST_VAR"])
        cfg = ai_config.load(self.path)
        with self.assertRaises(KeyError):
            ai_config.resolve_api_key(cfg.key_source)

    def test_ai_test_with_fake_provider(self):
        cli.main(["ai", "setup", "--base-url", "https://x.test/v1",
                  "--model", "m", "--key-source", "none"])
        with patch("fanmon.ai.provider.OpenAICompatProvider.chat",
                   return_value={"role": "assistant", "content": "OK"}):
            self.assertEqual(cli.main(["ai", "test"]), 0)

    def test_ai_test_unconfigured(self):
        self.assertEqual(cli.main(["ai", "test"]), 2)


if __name__ == "__main__":
    unittest.main()
