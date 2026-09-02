#!/usr/bin/env bash
# Rehearse a PyPI install: build the wheel, install it into a clean venv,
# and prove the `fm` entry point works. Mirrors sinter's verify-package.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

tmp="$(mktemp -d)"
cleanup() { rm -rf -- "$tmp"; }
trap cleanup EXIT

echo "==> build wheel"
rm -rf "$ROOT"/dist "$ROOT"/*.egg-info
python3 -m pip wheel "$ROOT" --no-deps -w "$ROOT/dist" -q
tarballs=("$ROOT"/dist/*.whl)
if [[ ${#tarballs[@]} -ne 1 || ! -f "${tarballs[0]}" ]]; then
  echo "expected exactly one wheel" >&2
  exit 1
fi

echo "==> wheel contents"
contents="$(python3 -m zipfile -l "${tarballs[0]}" | awk 'NR>1 {print $1}')"
for required in fanmon/fanmon.tcss fanmon/cli.py fanmon/app.py; do
  if ! grep -qx "$required" <<<"$contents"; then
    echo "wheel is missing $required" >&2
    exit 1
  fi
done

expected="$(FANMON_INIT="$ROOT/fanmon/__init__.py" python3 -c \
  'import re,os; print(re.search(r"__version__ = \"([^\"]+)\"", open(os.environ["FANMON_INIT"]).read()).group(1))')"
actual="$(basename "${tarballs[0]}" | sed -E 's/^macos_fanmon-([^-]+)-.*/\1/')"
if [[ "$actual" != "$expected" ]]; then
  echo "wheel version $actual does not match package version $expected" >&2
  exit 1
fi

echo "==> install into clean venv"
python3 -m venv "$tmp/venv"
# deps (rich, textual) resolve from PyPI; only the wheel itself comes from dist/
"$tmp/venv/bin/pip" install -q "${tarballs[0]}"

echo "==> smoke test"
"$tmp/venv/bin/fm" --help >/dev/null
"$tmp/venv/bin/fm" --once --warmup 0.3 >/dev/null

echo "verified pip install + fm entry point for macos-fanmon@$expected"
