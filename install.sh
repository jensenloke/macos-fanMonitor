#!/usr/bin/env bash
# Set up the venv, install deps, and (optionally) link `fm` onto PATH.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> venv"
python3 -m venv "$DIR/.venv"
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
