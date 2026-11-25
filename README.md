# Chip & Cell

Korean Semiconductor & Battery Stocks — Data & Deep Dives. https://chipandcell.com

- `site/` — Astro static site (Vercel)
- `pipeline/` — daily data export + post generation (runs on mini via launchd, 18:10 KST)

Docs: `docs/superpowers/specs/` (design), `docs/superpowers/plans/` (implementation).

## 운영 상태 확인

배치가 조용히 실패하지 않도록 세 가지 장치가 있다. 외부 알림(텔레그램 등)은 설계상 쓰지 않는다.

| 무엇 | 어디 | 보는 법 |
|---|---|---|
| 단계별 성공/실패·사유 | `pipeline/state/status.json` (gitignore) | `cat pipeline/state/status.json` |
| 배치 로그 | `logs/daily_YYYYMMDD.log` | 마지막 줄의 `done with FAILURES: ...` |
| 발행 데이터 자체 검사 | `python3 -m pipeline.healthcheck` | 실패가 있으면 종료 코드 1 |

`run_daily.sh`는 어느 단계든 실패하면 마지막에 요약을 찍고 **종료 코드 1**로 끝난다(launchd 로그에 남는다).
`healthcheck`는 수치 모순(0.00%가 장부와 어긋남), 수급 누락, 심층 글·주간 리뷰 누락, 지수 스테일을 검사한다.

```bash
python3 -m pipeline.healthcheck                  # 현재 발행 상태 점검
python3 -m pipeline.healthcheck --json           # 기계 판독용
python3 -m pytest -q                             # 파이프라인 테스트(네트워크 불필요)
```

## 수급 데이터 경로

1. `pipeline.flow_history`가 KIS에서 30거래일치를 받아 `site/src/data/history/flows.json`에 쌓는다(원장).
2. `pipeline.export_data`는 그 원장에서 종목별 스냅샷 일자 행을 읽어 `flow`를 채운다. 원장에 없을 때만
   KIS를 직접 부르고, 이때 토큰은 **실행당 1회**만 발급한다(KIS는 1분 1회 제한).

두 경로 모두 실패하면 `flow: null`과 함께 `stocks.json`의 `flow_status`·`status.json`에 사유가 남는다.
