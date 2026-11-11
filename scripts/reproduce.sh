#!/usr/bin/env bash
# Usage, from a clean Linux machine with Python 3.10+ and no GPU:
#   scripts/reproduce.sh serve     start POST /ask and GET /healthz on $PORT (default 8000)
#   scripts/reproduce.sh eval      run the dev set, grade it, append the run to results/manifest.json
#   scripts/reproduce.sh test      safety checks, no API key needed
#   scripts/reproduce.sh load      service-side latency at concurrency 12 against a stub model
# Inputs: CORPUS_DIR (manifest.jsonl, passages.jsonl, text/), LLM_BASE_URL, LLM_API_KEY.
# Optional: GEN_MODEL (default qwen/qwen3.8-27b, tested on Groq), GEN_EXTRA, JUDGE_MODEL, REF_DIR.
# A local .env file is loaded if present.
# The index is rebuilt from CORPUS_DIR on every start; nothing is cached on disk.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then set -a; . ./.env; set +a; fi
export REF_DIR="${REF_DIR:-../hiring-problems/references/OP-05}"
export CORPUS_DIR="${CORPUS_DIR:-$REF_DIR/corpus}"

if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
# Dependencies: already installed (image or earlier run), else ./wheels (no network), else PyPI.
if ! .venv/bin/python -c "import bm25s, fastapi, openai, uvicorn" 2>/dev/null; then
  { [ -d wheels ] && .venv/bin/python -m pip install -q --no-index --find-links wheels -r requirements.txt; } \
    || .venv/bin/python -m pip install -q -r requirements.txt
fi

case "${1:-}" in
  serve) exec .venv/bin/uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" ;;
  eval)  shift; exec .venv/bin/python evaluate.py "$@" ;;
  test)  exec .venv/bin/python test_app.py ;;
  load)  exec .venv/bin/python scripts/loadtest.py ;;
  proxy) exec .venv/bin/python scripts/pacing_proxy.py ;;  # dev only: paces calls on rate-limited tiers
  *)     sed -n '2,10p' "$0"; exit 2 ;;
esac
