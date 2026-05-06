#!/bin/sh
set -eu

CODE_ROOT="${MIHOYO_CODE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
PYTHON_BIN="${MIHOYO_VENV_PYTHON:-$CODE_ROOT/.venv/bin/python}"

cd "$CODE_ROOT"
exec "$PYTHON_BIN" "$CODE_ROOT/main.py"
