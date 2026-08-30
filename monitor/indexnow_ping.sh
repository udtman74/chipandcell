#!/bin/bash
# chipandcell.com IndexNow 주간 핑 — sitemap 전 URL을 api.indexnow.org에 제출 (빙·얀덱스 등)
# launchd: com.chipandcell.indexnow (매주 월 09:50, 미니)
# 로그: monitor/logs/indexnow_YYYYMM.log (전체 보존 — tail/덮어쓰기 금지 원칙)
set -u
HOST="chipandcell.com"
KEY="174c7961a3143fcfb3d7b8d2043f0529"
SITEMAP="https://chipandcell.com/sitemap-0.xml"
LOGDIR="$(dirname "$0")/logs"
LOG="$LOGDIR/indexnow_$(date +%Y%m).log"
mkdir -p "$LOGDIR"

ts() { date "+%Y-%m-%d %H:%M:%S"; }
echo "[$(ts)] indexnow_ping start" >> "$LOG"

XML=$(curl -s --max-time 30 "$SITEMAP")
if [ -z "$XML" ]; then
  echo "[$(ts)] ERROR: sitemap fetch failed" >> "$LOG"
  exit 1
fi

URLS=$(echo "$XML" | grep -oE '<loc>[^<]+</loc>' | sed -E 's#</?loc>##g')
COUNT=$(echo "$URLS" | grep -c .)
if [ "$COUNT" -lt 10 ]; then
  echo "[$(ts)] ERROR: only $COUNT urls parsed — abort (sitemap 이상 의심)" >> "$LOG"
  exit 1
fi

PAYLOAD=$(echo "$URLS" | /usr/bin/python3 -c "
import json, sys
urls = [u.strip() for u in sys.stdin if u.strip()]
print(json.dumps({
    'host': '$HOST',
    'key': '$KEY',
    'keyLocation': 'https://$HOST/$KEY.txt',
    'urlList': urls,
}))
")

HTTP=$(curl -s -o /tmp/indexnow_resp.txt -w "%{http_code}" --max-time 30 \
  -X POST "https://api.indexnow.org/indexnow" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "$PAYLOAD")

if [ "$HTTP" = "200" ] || [ "$HTTP" = "202" ]; then
  echo "[$(ts)] OK: $COUNT urls submitted, HTTP $HTTP" >> "$LOG"
else
  echo "[$(ts)] ERROR: HTTP $HTTP body=$(cat /tmp/indexnow_resp.txt | head -c 200)" >> "$LOG"
  exit 1
fi
