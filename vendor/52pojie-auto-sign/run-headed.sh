#!/usr/bin/env bash
set -euo pipefail

CODE_ROOT="${POJIE_CODE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
PROJECT_ROOT="${POJIE_PROJECT_ROOT:-$CODE_ROOT}"

cd "$PROJECT_ROOT"
export DISPLAY="${DISPLAY:-:1}"
export POJIE_HEADLESS="${POJIE_HEADLESS:-false}"
export POJIE_HUMAN_MODE="${POJIE_HUMAN_MODE:-true}"
export POJIE_TIMEZONE_ID="${POJIE_TIMEZONE_ID:-Asia/Shanghai}"
export POJIE_SLOW_MO_MS="${POJIE_SLOW_MO_MS:-90}"
NODE_BIN="${NODE_BIN:-node}"

exec "$NODE_BIN" "$CODE_ROOT/scripts/signin.mjs"
