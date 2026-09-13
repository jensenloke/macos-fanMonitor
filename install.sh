#!/usr/bin/env bash
# Set up the venv, install deps, and (optionally) link `fm` onto PATH.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON="${PYTHON:-python3}"

# fm needs Python 3.11+ (stdlib tomllib for the config file).
VER="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")"
if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "fm needs Python 3.11+; found $VER —" >&2
  echo "try \`brew install python@3.12\` and re-run with" >&2
  echo "  PYTHON=/opt/homebrew/bin/python3.12 ./install.sh" >&2
  exit 1
fi

echo "==> venv ($PYTHON $VER)"
"$PYTHON" -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

chmod +x "$DIR/fm"

# Link onto PATH if ~/.local/bin exists or can be created.
BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"
ln -sf "$DIR/fm" "$BIN_DIR/fm"
echo "==> linked: $BIN_DIR/fm -> $DIR/fm"
echo "    make sure $BIN_DIR is on your PATH."

echo
echo "Done. Try:"
echo "  $DIR/fm --once     # single snapshot"
echo "  $DIR/fm            # live dashboard (Ctrl-C to quit)"
echo
echo "Optional AI second opinion:"
echo "  fm ai providers    # see what's reachable"
echo "  fm ai setup …      # e.g. --from-omp dgx, or --key-source env:VAR|none"
