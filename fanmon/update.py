"""Self-update: PyPI version check, cache, and upgrade.

Checks https://pypi.org/pypi/macos-fanmon/json at most every 12h from a
background thread; a newer cached version upgrades on the next launch when
[update] auto = true (the default). `FANMON_NO_UPDATE=1` disables everything.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass

from . import __version__

PYPI_URL = "https://pypi.org/pypi/macos-fanmon/json"
CHECK_EVERY_S = 12 * 3600
UPGRADE_TIMEOUT = 120


@dataclass
class Cache:
    latest: str = ""
    checked_at: float = 0.0
    current: str = ""
    attempted: str = ""


def cache_path() -> str:
    return os.environ.get("FANMON_UPDATE_CACHE") or os.path.expanduser(
        "~/.cache/macos-fanMonitor/update.json")


def read_cache() -> Cache | None:
    try:
        with open(cache_path()) as f:
            d = json.load(f)
        return Cache(str(d.get("latest", "")), float(d.get("checked_at", 0)),
                     str(d.get("current", "")), str(d.get("attempted", "")))
    except Exception:
        return None


def write_cache(latest: str, attempted: str = "") -> None:
    try:
        os.makedirs(os.path.dirname(cache_path()), exist_ok=True)
        with open(cache_path(), "w") as f:
            json.dump({"latest": latest, "checked_at": time.time(),
                       "current": __version__, "attempted": attempted}, f)
    except Exception:
        pass


def mark_attempted() -> None:
    """Record that we already tried upgrading to the cached 'latest'."""
    c = read_cache()
    if c:
        write_cache(c.latest, attempted=c.latest)


def is_newer(a: str, b: str) -> bool:
    """Dotted-int compare; non-numeric suffixes are ignored."""
    def parts(v):
        out = []
        for tok in str(v).split("."):
            num = ""
            for ch in tok:
                if ch.isdigit():
                    num += ch
                else:
                    break
            out.append(int(num) if num else 0)
        return tuple(out)
    return parts(a) > parts(b)


def detect_install() -> str:
    pkg = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(pkg)
    if os.path.isdir(os.path.join(repo, ".git")) and \
            os.path.isdir(os.path.join(repo, ".venv")):
        return "repo"
    if "/pipx/" in sys.executable:
        return "pipx"
    return "pip"


def check_latest(timeout: float = 2.0) -> str | None:
    try:
        import urllib.request
        with urllib.request.urlopen(PYPI_URL, timeout=timeout) as r:
            return json.loads(r.read().decode())["info"]["version"]
    except Exception:
        return None


def run_upgrade(method: str) -> tuple:
    """(ok, log). Clears the cached 'latest' on success."""
    pkg = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(pkg)
    cmds = {
        "repo": [["git", "-C", repo, "pull", "--ff-only"],
                 [os.path.join(repo, ".venv", "bin", "pip"), "install",
                  "--quiet", "-r", os.path.join(repo, "requirements.txt")]],
        "pipx": [["pipx", "upgrade", "macos-fanmon"]],
        "pip": [[sys.executable, "-m", "pip", "install", "--quiet", "-U",
                 "macos-fanmon"]],
    }[method]
    log = ""
    try:
        for cmd in cmds:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=UPGRADE_TIMEOUT)
            log += p.stdout + p.stderr
            if p.returncode != 0:
                return False, log
        mark_attempted()
        return True, log
    except Exception as e:
        return False, log + str(e)


def _auto_enabled() -> bool:
    from .ai import config as ai_config
    cfg = ai_config.load()
    return cfg.update.auto if cfg else True


def launch_check(print_line=print) -> None:
    """Called from cli.main before the TUI / --once runs. Never raises."""
    if os.environ.get("FANMON_NO_UPDATE", "").strip().lower() in \
            {"1", "true", "yes", "on"}:
        return
    try:
        cache = read_cache()
        tried = cache and cache.attempted == cache.latest \
            and cache.current == __version__
        if cache and cache.latest and is_newer(cache.latest, __version__) \
                and not tried:
            if not _auto_enabled():
                return
            method = detect_install()
            print_line(f"fm: updating {__version__} → {cache.latest}…")
            ok, log = run_upgrade(method)
            if ok:
                print_line(f"fm: updated to {cache.latest}")
                env = os.environ
                if method == "repo":
                    repo = os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__)))
                    env["PYTHONPATH"] = repo + os.pathsep + \
                        env.get("PYTHONPATH", "")
                os.execv(sys.executable,
                         [sys.executable, "-m", "fanmon", *sys.argv[1:]])
            else:
                print_line(f"fm: auto-update failed "
                           f"({log.strip().splitlines()[-1][:80] if log.strip() else '?'})"
                           f" — try `fm update`")
            return
        if cache is None or time.time() - cache.checked_at > CHECK_EVERY_S:
            import threading
            def _bg():
                latest = check_latest()
                if latest:
                    write_cache(latest)
            threading.Thread(target=_bg, daemon=True).start()
    except Exception:
        return
