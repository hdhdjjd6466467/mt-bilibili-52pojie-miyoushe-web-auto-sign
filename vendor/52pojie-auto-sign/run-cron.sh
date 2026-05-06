#!/usr/bin/env bash
set -euo pipefail

CODE_ROOT="${POJIE_CODE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
PROJECT_ROOT="${POJIE_PROJECT_ROOT:-$CODE_ROOT}"

cd "$PROJECT_ROOT"
mkdir -p "$PROJECT_ROOT/logs"

export DISPLAY="${DISPLAY:-:1}"
export POJIE_HEADLESS="${POJIE_HEADLESS:-false}"
export POJIE_HUMAN_MODE="${POJIE_HUMAN_MODE:-true}"
export POJIE_TIMEZONE_ID="${POJIE_TIMEZONE_ID:-Asia/Shanghai}"
export POJIE_SLOW_MO_MS="${POJIE_SLOW_MO_MS:-90}"
PYTHON_BIN="${POJIE_PYTHON_BIN:-python3}"
retry_count="${POJIE_RETRY_COUNT:-3}"
retry_sleep_seconds="${POJIE_RETRY_SLEEP_SECONDS:-120}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "$(date -Is) [run-cron] missing python interpreter: $PYTHON_BIN" >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY'
from importlib.util import find_spec
required = ["ddddocr", "PIL"]
missing = [name for name in required if find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
then
  echo "$(date -Is) [run-cron] missing python packages in $PYTHON_BIN: ddddocr and/or pillow" >&2
  exit 1
fi

if ! command -v tesseract >/dev/null 2>&1; then
  echo "$(date -Is) [run-cron] warning: tesseract not found, fallback OCR disabled" >&2
fi

for ((attempt = 1; attempt <= retry_count; attempt += 1)); do
  echo "$(date -Is) [run-cron] attempt ${attempt}/${retry_count}"
  if "$CODE_ROOT/run-headed.sh"; then
    exit 0
  fi

  exit_code=$?
  if (( attempt == retry_count )); then
    echo "$(date -Is) [run-cron] final failure exit=${exit_code}" >&2
    exit "${exit_code}"
  fi

  echo "$(date -Is) [run-cron] attempt ${attempt} failed exit=${exit_code}, retry in ${retry_sleep_seconds}s" >&2
  sleep "${retry_sleep_seconds}"
done
