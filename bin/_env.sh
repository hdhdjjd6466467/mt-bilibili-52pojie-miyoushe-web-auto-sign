#!/usr/bin/env bash
set -euo pipefail

SELF_PATH="${BASH_SOURCE[0]-$0}"
if [[ "$SELF_PATH" == "bash" || "$SELF_PATH" == "-bash" || "$SELF_PATH" == "zsh" || "$SELF_PATH" == "-zsh" ]]; then
  SELF_PATH="$(pwd)/bin/_env.sh"
fi
ROOT="$(cd "$(dirname "$SELF_PATH")/.." && pwd)"

if [[ -x "$ROOT/runtime/python/bin/python3" ]]; then
  export SIGNADMIN_PYTHON_BIN="$ROOT/runtime/python/bin/python3"
elif [[ -x "$ROOT/runtime/python/python.exe" ]]; then
  export SIGNADMIN_PYTHON_BIN="$ROOT/runtime/python/python.exe"
fi

if [[ -d "$ROOT/runtime/ms-playwright" ]]; then
  export PLAYWRIGHT_BROWSERS_PATH="$ROOT/runtime/ms-playwright"
fi

if [[ -x "$ROOT/runtime/node/bin/node" ]]; then
  export SIGNADMIN_NODE_BIN="$ROOT/runtime/node/bin/node"
  export NODE_BIN="$ROOT/runtime/node/bin/node"
  export PATH="$ROOT/runtime/node/bin:$PATH"
fi

if [[ -d "$ROOT/runtime/node/lib" ]]; then
  if [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
    export LD_LIBRARY_PATH="$ROOT/runtime/node/lib:$LD_LIBRARY_PATH"
  else
    export LD_LIBRARY_PATH="$ROOT/runtime/node/lib"
  fi
fi
