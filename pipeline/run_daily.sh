#!/bin/zsh
# Chip & Cell 일일 배치(미니): flow_history → export → 글 생성 → commit → push (Vercel 자동배포)
#
# 실패를 조용히 흘려보내지 않는다 (2026-11-15 수정):
#  - 각 단계의 종료 코드를 FAILED 배열에 모아 마지막에 요약하고, 하나라도 실패하면 스크립트가
#    종료 코드 1로 끝난다 → launchd 로그에 실패가 남는다. 예전에는 `|| echo` 뒤에 `echo done`이
#    있어 어떤 실패도 최종 코드 0이 됐고, 2주간 심층 글 6일·주간 리뷰 2회 누락이 지나갔다.
#  - 글 생성 단계는 pipeline/state/status.json에 사유를 남기고 비0으로 끝난다.
#  - 수급 원장(flow_history)을 export보다 먼저 돌린다. export는 오늘자 수급을 원장에서 읽으므로
#    27종목이 각자 토큰을 발급받아 전부 실패하던 경로가 사라진다.
#  - 텔레그램 등 외부 알림은 설계상 금지 — 상태 파일·종료 코드·로그만 쓴다.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=logs/daily_$(date +%Y%m%d).log
mkdir -p logs pipeline/state

FAILED=()
run_step() {                     # run_step <이름> <명령...> — 실패해도 다음 단계로 진행
  local name="$1"; shift
  "$@"
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "❌ $name FAILED (exit $rc)"
    FAILED+=("$name")
  fi
  return 0
}

{
  echo "=== $(date '+%F %T') start ==="
  # Gemini 키: kr-screener .env의 GEMINI_FREE_API_KEY만 유효(GOOGLE_API_KEY는 8/30 실측 INVALID).
  # 못 찾으면 llm.py가 Ollama로 폴백.
  if [ -f ~/kr-stock-screener/.env ]; then
    _gk=$(grep -E '^GEMINI_FREE_API_KEY=' ~/kr-stock-screener/.env | head -1 | cut -d= -f2-)
    [ -n "$_gk" ] && export GEMINI_API_KEY="$_gk"
  fi
  git pull --rebase origin main || { echo "PULL FAILED"; exit 1; }
  PY=.venv/bin/python
  [ -x "$PY" ] || PY=python3

  # 1) 수급 원장 먼저 (export가 이 원장을 읽는다)
  run_step flow_history "$PY" -m pipeline.flow_history
  # 2) 시세·수급 export — 실패하면 발행할 데이터가 없으므로 중단
  "$PY" -m pipeline.export_data || { echo "EXPORT FAILED"; exit 1; }
  # 3) 이하 단계는 실패해도 후속을 막지 않되, 실패로 집계한다.
  run_step record_ledger "$PY" -m pipeline.record_ledger
  run_step verify_ledger "$PY" -m pipeline.verify_ledger
  run_step valuechain "$PY" -m pipeline.valuechain
  run_step charts "$PY" -m pipeline.charts
  run_step gen_deep_dive "$PY" -m pipeline.gen_deep_dive
  run_step gen_weekly "$PY" -m pipeline.gen_weekly
  # 4) 발행 결과 자체를 검사(수치 모순·수급 누락·글 누락)
  run_step healthcheck "$PY" -m pipeline.healthcheck --expect-today "$(date +%F)"

  git add site/src/data site/src/content/posts
  if ! git diff --cached --quiet; then
    git commit -m "data: daily refresh $(date +%F)"
    git push origin main || { echo "PUSH FAILED"; exit 1; }
  else
    echo "no changes"
  fi

  if (( ${#FAILED[@]} )); then
    echo "=== $(date '+%F %T') done with FAILURES: ${FAILED[*]} ==="
    echo "    상태: pipeline/state/status.json · 로그: $LOG"
    exit 1
  fi
  echo "=== $(date '+%F %T') done ==="
} 2>&1 | tee -a "$LOG"
