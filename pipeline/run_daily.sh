#!/bin/zsh
# Chip & Cell 일일 배치(미니): export → 글 생성 → commit → push (Vercel 자동배포)
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=logs/daily_$(date +%Y%m%d).log
mkdir -p logs
{
  echo "=== $(date '+%F %T') start ==="
  # Gemini 키: kr-screener 로컬 .env 재사용(GOOGLE_API_KEY 우선, 없으면 GEMINI_FREE_API_KEY).
  # 못 찾으면 llm.py가 Ollama로 폴백.
  if [ -f ~/kr-stock-screener/.env ]; then
    _gk=$(grep -E '^(GOOGLE_API_KEY|GEMINI_FREE_API_KEY)=' ~/kr-stock-screener/.env | head -1 | cut -d= -f2-)
    [ -n "$_gk" ] && export GEMINI_API_KEY="$_gk"
  fi
  git pull --rebase origin main
  PY=.venv/bin/python
  [ -x "$PY" ] || PY=python3
  "$PY" -m pipeline.export_data || { echo "EXPORT FAILED"; exit 1; }
  "$PY" -m pipeline.gen_deep_dive
  "$PY" -m pipeline.gen_weekly
  git add site/src/data site/src/content/posts
  if ! git diff --cached --quiet; then
    git commit -m "data: daily refresh $(date +%F)"
    git push origin main || { echo "PUSH FAILED"; exit 1; }
  else
    echo "no changes"
  fi
  echo "=== $(date '+%F %T') done ==="
} 2>&1 | tee -a "$LOG"
