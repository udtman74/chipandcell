"""발행 데이터 점검 — 숫자가 장부와 어긋나거나 글이 빠진 상태를 감지한다.

용도
1. `run_daily.sh` 마지막 단계: 그날 배치가 남긴 결과를 검사해 실패를 종료 코드로 알린다.
2. 사람·AI 점검: `python3 -m pipeline.healthcheck` 로 언제든 현재 발행 상태를 확인한다.

검사 항목 (FAIL이 하나라도 있으면 종료 코드 1)

A. 구조: stocks.json/asof·27종목·종목 날짜가 asof보다 미래가 아닌지 (스테일 종목은 WARN)
B. 자기 일관성: `bases`(기준일 종가)로 pct/r5/r20/r60을 다시 계산해 비교
C. 0.00% 감사: 0.00%로 적힌 값이 장부(ledger.json)의 같은 날짜 종가와 모순되지 않는지
   — 2026-11-13의 가온칩스 r20 0.00%, 천보 당일 0.00%가 정확히 이 모순이었다.
D. 장부 대조: 나머지 수익률이 장부 종가와 크게 어긋나면 WARN(피드 개정 추적)
E. 수급 커버리지: flows.json에 그 날짜 행이 있는데 stocks.json의 flow가 null이면 FAIL
   — 2026-11-13의 27종목 전면 누락이 이 경우다.
F. 심층 글: 장부의 최근 거래일 5일 각각에 글이 있는지 (없으면 FAIL)
G. 주간 리뷰: 최근 14일 안의 금요일 글 (없으면 FAIL)
H. 시장 지수 stale 플래그 (WARN)

블로그 관련 외부 알림(텔레그램 등)은 설계상 금지이므로 이 도구는 파일과 종료 코드로만 알린다.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from pipeline import status as runstatus
from pipeline.metrics import implied_base, inconsistencies

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "..", "site", "src", "data")
POSTS = os.path.join(_DIR, "..", "site", "src", "content", "posts")

DEEP_DIVE_WINDOW = 5          # 최근 거래일 몇 일치 글을 요구할지
WEEKLY_WINDOW_DAYS = 14
ZERO_TOL = 0.1                # 0.00% 감사 허용 오차(%p)
WARN_TOL = 0.3                # 장부 대조 WARN 기준(%p)


def _load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _fridays(upto, days=WEEKLY_WINDOW_DAYS):
    d = datetime.strptime(upto, "%Y-%m-%d")
    out = []
    for i in range(days):
        day = d - timedelta(days=i)
        if day.weekday() == 4:
            out.append(day.strftime("%Y-%m-%d"))
    return out


def _post_dates(posts_dir):
    """content/posts 파일명에서 (날짜, slug) 목록."""
    out = []
    try:
        names = sorted(os.listdir(posts_dir))
    except Exception:
        return out
    for n in names:
        if not n.endswith(".md") or len(n) < 11:
            continue
        out.append((n[:10], n[11:-3]))
    return out


def _ledger_index(ledger):
    """{code: {date: close}} + 거래일 목록(모든 종목에 공통인 날짜)."""
    closes, dates = {}, {}
    for r in ledger.get("records", []):
        closes.setdefault(r["code"], {})[r["date"]] = r.get("close")
        dates[r["date"]] = dates.get(r["date"], 0) + 1
    return closes, sorted(dates)


def _session_before(dates, date, n):
    """거래일 목록에서 date보다 n세션 앞선 날짜."""
    try:
        i = dates.index(date)
    except ValueError:
        return None
    return dates[i - n] if i >= n else None


def check(data_dir=None, posts_dir=None, expect_today=None):
    """검사 실행. {'checks': [...], 'failed': [...], 'warned': [...]} 반환."""
    data_dir = data_dir or DATA
    posts_dir = posts_dir or POSTS
    checks = []

    def add(cid, status, detail):
        checks.append({"id": cid, "status": status, "detail": detail})

    stocks_doc = _load(os.path.join(data_dir, "stocks.json"))
    if not stocks_doc or "stocks" not in stocks_doc:
        add("stocks.json", "fail", "읽을 수 없거나 stocks 키가 없음")
        return _report(checks)
    stocks, asof = stocks_doc["stocks"], stocks_doc.get("asof")
    ledger = _load(os.path.join(data_dir, "history", "ledger.json"), {"records": []})
    flows = _load(os.path.join(data_dir, "history", "flows.json"), {"flows": {}})
    closes, dates = _ledger_index(ledger)

    # A. 구조
    future = [c for c, s in stocks.items() if s.get("date", "") > (asof or "")]
    stale = [c for c, s in stocks.items() if s.get("stale") or s.get("date", "") < (asof or "")]
    if not asof or len(stocks) != 27:
        add("stocks.structure", "fail", f"asof={asof} 종목수={len(stocks)} (기대 27)")
    elif future:
        add("stocks.structure", "fail", f"asof {asof}보다 미래 날짜 종목: {future}")
    else:
        add("stocks.structure", "pass", f"asof={asof} 종목={len(stocks)}")
    if stale:
        add("stocks.stale", "warn", f"asof {asof}에 못 미친 종목 {len(stale)}개: {stale}")

    # B. 자기 일관성 (기준일 종가로 재계산)
    bad = []
    for code, s in stocks.items():
        for field, expect, actual, tol in inconsistencies(s):
            bad.append(f"{code}.{field} 기대 {expect} 실제 {actual}")
    has_bases = any(s.get("bases") for s in stocks.values())
    add("metrics.self_consistent", "fail" if bad else "pass",
        "; ".join(bad[:5]) if bad else
        ("bases 기준 재계산 일치" if has_bases else "bases 없음(구 형식) — 다음 export부터 기록"))

    # C. 0.00% 감사 — 0.00%는 같은 종가를 두 번 비교했을 때도 만들어진다.
    zero_bad = []
    for code, s in stocks.items():
        close, per = s.get("close"), (closes.get(code) or {})
        p = s.get("prev_date") or _session_before(dates, s.get("date"), 1)
        if p and per.get(p) and s.get("pct") == 0.0 and abs(per[p] - close) > 0.001:
            zero_bad.append(f"{code} 당일 0.00%인데 장부 {p} 종가 {per[p]:,} ≠ {close:,}")
        for n, field in ((5, "r5"), (20, "r20"), (60, "r60")):
            if s.get(field) != 0.0:
                continue
            base = (s.get("bases") or {}).get(field) or {}
            bdate = base.get("date") or _session_before(dates, s.get("date"), n)
            bclose = per.get(bdate) if bdate else None
            if bclose and abs(bclose / close - 1) * 100 > ZERO_TOL:
                imp = implied_base(close, s.get(field)) or 0
                zero_bad.append(f"{code} {field} 0.00%인데 장부 {bdate} 종가 {bclose:,} "
                                f"≠ {close:,} (발행값이 말하는 기준가 ≈ {imp:,.0f})")
    add("metrics.zero_return", "fail" if zero_bad else "pass",
        "; ".join(zero_bad[:5]) if zero_bad else "0.00% 값이 장부와 모순되지 않음")

    # D. 장부 대조 (피드 개정 추적, WARN)
    drift = []
    for code, s in stocks.items():
        per, close = closes.get(code) or {}, s.get("close")
        if not close:
            continue
        for field, n in (("r5", 5), ("r20", 20), ("r60", 60)):
            val = s.get(field)
            if val is None or val == 0.0:
                continue
            bdate = ((s.get("bases") or {}).get(field) or {}).get("date") \
                or _session_before(dates, s.get("date"), n)
            bclose = per.get(bdate) if bdate else None
            if not bclose:
                continue
            expect = (close / bclose - 1) * 100
            if abs(expect - val) > WARN_TOL:
                drift.append(f"{code}.{field} 장부 {expect:+.2f}% vs 발행 {val:+.2f}% ({bdate})")
    add("metrics.ledger_drift", "warn" if drift else "pass",
        "; ".join(drift[:5]) if drift else "장부와 큰 차이 없음")

    # E. 수급 커버리지
    covered = sum(1 for s in stocks.values() if s.get("flow"))
    flow_at_asof = sum(1 for c in stocks if (flows.get("flows", {}).get(c) or {}).get(asof))
    fs = stocks_doc.get("flow_status") or {}
    if covered == len(stocks):
        add("flow.coverage", "pass", f"{covered}/{len(stocks)} (원천 {fs.get('sources')})")
    elif flow_at_asof >= len(stocks) // 2:
        add("flow.coverage", "fail",
            f"{covered}/{len(stocks)}만 채워짐 — flows.json에는 {asof} 행이 {flow_at_asof}종목 있음. "
            f"이유: {fs.get('reason')}")
    else:
        add("flow.coverage", "warn",
            f"{covered}/{len(stocks)}만 채워짐 — flows.json에도 {asof} 행이 없음(상류 실패). "
            f"이유: {fs.get('reason')}")

    # F. 심층 글 커버리지
    posts = _post_dates(posts_dir)
    have = {d for d, _slug in posts if not _slug.endswith("weekly-review")}
    window = dates[-DEEP_DIVE_WINDOW:]
    missing = [d for d in window if d not in have]
    add("posts.deep_dive", "fail" if missing else "pass",
        f"최근 거래일 {len(window)}일 중 누락 {missing}" if missing
        else f"최근 거래일 {len(window)}일 모두 있음")

    # G. 주간 리뷰
    weekly_have = {d for d, slug in posts if slug.endswith("weekly-review")}
    fridays = _fridays(asof) if asof else []
    missing_weekly = [d for d in fridays if d not in weekly_have]
    add("posts.weekly", "fail" if missing_weekly else "pass",
        f"금요일 주간 리뷰 누락 {missing_weekly}" if missing_weekly
        else f"최근 {WEEKLY_WINDOW_DAYS}일 금요일 리뷰 있음")

    # H. 오늘 배치 기대치 (run_daily.sh가 켜서 부른다)
    if expect_today:
        today = expect_today
        if today not in have:
            add("posts.today", "fail", f"{today} 심층 글 없음")
        elif datetime.strptime(today, "%Y-%m-%d").weekday() == 4 and today not in weekly_have:
            add("posts.today_weekly", "fail", f"{today} 주간 리뷰 없음")
        else:
            add("posts.today", "pass", f"{today} 글 생성 확인")

    # I. 시장 지수 stale
    market = _load(os.path.join(data_dir, "market.json"), {})
    staled = [k for k in ("kospi", "kosdaq") if (market.get(k) or {}).get("stale")]
    if staled:
        add("market.stale", "warn", f"지수 stale: {staled}")
    else:
        add("market.stale", "pass", "지수 최신")

    return _report(checks)


def _report(checks):
    failed = [c["id"] for c in checks if c["status"] == "fail"]
    warned = [c["id"] for c in checks if c["status"] == "warn"]
    return {"checks": checks, "failed": failed, "warned": warned,
            "ok": not failed, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def render(rep):
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    lines = [f"chipandcell healthcheck {rep['at']}"]
    for c in rep["checks"]:
        lines.append(f"  {icon[c['status']]} {c['id']}: {c['detail']}")
    lines.append("  → " + ("OK" if rep["ok"] else f"FAILED: {', '.join(rep['failed'])}"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-today", help="YYYY-MM-DD (배치: 오늘 글 생성 여부까지 검사)")
    ap.add_argument("--json", action="store_true", help="기계 판독용 JSON 출력")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    rep = check(expect_today=args.expect_today)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    elif not args.quiet:
        print(render(rep))
    runstatus.record("healthcheck", "ok" if rep["ok"] else "failed",
                     reason=None if rep["ok"] else f"{rep['failed']}",
                     extra={"warned": rep["warned"]})
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
