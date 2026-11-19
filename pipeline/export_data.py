"""일일 데이터 export: fdr(시세) + KIS(수급) → site/src/data/*.json

수급 획득 경로 (2026-11-15 수정):

1. `site/src/data/history/flows.json` — `pipeline.flow_history`가 KIS에서 받아 매일 쌓는
   원장. 해당 종목의 스냅샷 일자 행이 있으면 그대로 쓴다(추가 호출 없음). 사이트 숫자와
   장부 숫자가 같은 출처를 갖게 되고, 2026-11-13처럼 원장에는 있는데 사이트는 전부 null인
   상태가 생기지 않는다.
2. 1)에 그 날짜 행이 없을 때만 KIS 직접 조회. **토큰은 실행당 1회만** 발급한다.
   예전 코드는 종목마다 `get_access_token()`을 불러 27회 발급을 시도했고, KIS는 토큰 발급을
   1분에 1회로 제한하므로 첫 종목 이후가 전부 실패 → `except Exception: return None`이
   사유를 삼켜 27종목 flow가 모두 null이 됐다.

실패는 조용히 넘어가지 않는다: 재시도·백오프 후 사유를 `pipeline/state/status.json`과
`stocks.json`의 `flow_status`에 남기고, "이 머신에 KIS가 없음(unavailable)"과
"조회 실패(failed)"를 구분해 기록한다(정직성 규칙: 없는 데이터를 추측하지 않는다).
"""
import json
import os
import sys
import time

from pipeline import status as runstatus
from pipeline.flow_history import load as load_flows
from pipeline.metrics import compute, inconsistencies
from pipeline.prices import read as read_prices
from pipeline.tickers import TICKERS, SECTOR_LABELS

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_DIR, "..", "site", "src", "data")

MAX_FLOW_ATTEMPTS = 3
FLOW_BACKOFF = (5.0, 20.0)      # 초. 실패할수록 길게
KIS_FIELDS = ("foreign_net", "inst_net", "individual_net")


class FlowFetchError(RuntimeError):
    """수급 조회 실패(사유 포함)."""


class FlowUnavailable(FlowFetchError):
    """이 머신에 KIS 연동(kis_api)이 없어 조회 자체가 불가능한 상태."""


class KISFlow:
    """KIS 수급 조회 어댑터. 토큰 1회 발급 + 재시도/백오프를 담당한다."""

    def __init__(self, api=None, sleep=None, attempts=MAX_FLOW_ATTEMPTS, backoff=FLOW_BACKOFF):
        self._api = api
        self._sleep = sleep or time.sleep
        self._attempts = attempts
        self._backoff = tuple(backoff)
        self._token = None
        self.token_requests = 0      # 테스트·진단용: 실행당 1이어야 정상
        self.fetches = 0

    def api(self):
        if self._api is not None:
            return self._api
        p = os.environ.get("CNC_SCREENER_PATH") or os.path.expanduser("~/kr-stock-screener")
        if p not in sys.path:
            sys.path.insert(0, p)
        import kis_api                                   # noqa: F401  (선택 의존성)
        return kis_api

    def available(self):
        try:
            api = self.api()
        except Exception:
            return False
        return all(hasattr(api, n) for n in ("get_access_token", "get_investor_trend"))

    def token(self):
        if self._token:
            return self._token
        self.token_requests += 1
        try:
            self._token = self.api().get_access_token()
        except (ImportError, ModuleNotFoundError) as e:
            raise FlowUnavailable(f"kis_api unavailable: {e}") from e
        except Exception as e:
            raise FlowFetchError(f"KIS token: {e.__class__.__name__}: {e}") from e
        if not self._token:
            raise FlowFetchError("empty KIS access token")
        return self._token

    def get(self, code):
        last = None
        for attempt in range(self._attempts):
            try:
                token = self.token()
                self.fetches += 1
                inv = self.api().get_investor_trend(code, token) or {}
                out = {k: inv[k] for k in KIS_FIELDS if k in inv}
                if not out:
                    raise FlowFetchError(f"{code}: empty investor trend")
                return out
            except (ImportError, ModuleNotFoundError) as e:
                raise FlowUnavailable(f"{code}: kis_api unavailable: {e}") from e
            except Exception as e:
                last = e
                if attempt + 1 < self._attempts:
                    self._sleep(self._backoff[min(attempt, len(self._backoff) - 1)])
        raise FlowFetchError(f"{code}: {last.__class__.__name__}: {last}")


def _flow_payload(flows, code, date):
    """flows.json의 {f,i,p} → 사이트 스키마."""
    row = (flows.get("flows", {}).get(code) or {}).get(date)
    if not row:
        return None
    return {"foreign_net": row.get("f"), "inst_net": row.get("i"),
            "individual_net": row.get("p"), "date": date, "source": "flows.json"}


def collect_flows(flows_store, dates, kis=None, log=print):
    """{code: date} → ({code: flow}, status dict).

    원장(flows.json) 우선, 없으면 KIS(토큰 1회). 실패는 종목별 사유로 남긴다.
    """
    flow, failures, src = {}, {}, {"flows.json": 0, "kis": 0, "missing": 0}
    # KIS가 정말 필요해질 때(원장에 없는 종목) 딱 한 번 준비한다: 토큰 1회 발급.
    # 예전 코드는 종목마다 토큰을 새로 받아 27회 시도하다 전부 실패했다.
    st = {"ok": bool(kis and kis.available()), "ready": False, "token_error": None,
          "unavailable": False}

    def kis_ready():
        if not st["ok"]:
            return False
        if st["ready"]:
            return True
        try:
            kis.token()
            st["ready"] = True
        except FlowUnavailable as e:
            st["ok"], st["token_error"] = False, str(e)
            st["unavailable"] = True
        except FlowFetchError as e:
            st["ok"], st["token_error"] = False, f"KIS token unavailable: {e}"
        except Exception as e:                       # 예상 밖 예외도 조용히 넘기지 않는다
            st["ok"], st["token_error"] = False, f"KIS token: {e.__class__.__name__}: {e}"
        return st["ready"]

    unavailable = 0
    for code, date in dates.items():
        payload = _flow_payload(flows_store, code, date)
        if payload:
            flow[code] = payload
            src["flows.json"] += 1
            continue
        if kis_ready():
            try:
                got = kis.get(code)
                flow[code] = {**got, "date": date, "source": "kis"}
                src["kis"] += 1
                continue
            except FlowUnavailable as e:
                failures[code] = str(e)
                unavailable += 1
            except FlowFetchError as e:
                failures[code] = str(e)
        else:
            failures[code] = st["token_error"] or \
                "KIS unavailable (kis_api not importable on this machine)"
            if st["token_error"] is None or st["unavailable"]:
                unavailable += 1
        src["missing"] += 1

    total, covered = len(dates), len(flow)
    reason = next(iter(failures.values()), None)
    if covered == total:
        state, reason = "ok", None
    elif covered == 0:
        state = "unavailable" if unavailable == total else "failed"
    else:
        state = "partial"
    if failures:
        log(f"  ⚠️ flow missing {len(failures)}/{total}: {reason}")
    return flow, {"status": state, "covered": covered, "total": total,
                  "sources": src, "failures": failures, "reason": reason}


def _sector_summary(stocks):
    sectors = {}
    for sec, label in SECTOR_LABELS.items():
        rows = {c: s for c, s in stocks.items() if s["sector"] == sec and s["r20"] is not None}
        if not rows:
            sectors[sec] = {"label": label, "median_r20": None, "advancers": 0,
                            "decliners": 0, "top": [], "bottom": []}
            continue
        rank = sorted(rows, key=lambda c: rows[c]["r20"], reverse=True)
        med = sorted(r["r20"] for r in rows.values())[len(rows) // 2]
        sectors[sec] = {
            "label": label,
            "median_r20": round(med, 2),
            "advancers": sum(1 for r in rows.values() if r["pct"] > 0),
            "decliners": sum(1 for r in rows.values() if r["pct"] < 0),
            "top": rank[:3],
            "bottom": rank[-3:],
        }
    return sectors


def _market(asof):
    """지수: 두 소스(네이버 KS11/KQ11, 야후 ^KS11/^KQ11) 중 가장 최신 날짜를 채택한다."""
    market = {}
    for key, syms in (("kospi", ("KS11", "^KS11")), ("kosdaq", ("KQ11", "^KQ11"))):
        best, errors = None, []
        for sym in syms:
            try:
                df = read_prices(sym)
            except Exception as e:
                errors.append(f"{sym}: {e!r}")
                continue
            if len(df) and "Close" in df.columns:
                try:
                    m = compute(df)
                except Exception as e:
                    errors.append(f"{sym}: {e!r}")
                    continue
                if best is None or m["date"] > best["date"]:
                    best = m
                if best["date"] >= asof:
                    break
        if best is None:
            raise SystemExit(f"export aborted: index fetch failed for {key} ({errors})")
        market[key] = {"close": best["close"], "pct": best["pct"], "r20": best["r20"],
                       "date": best["date"], "stale": best["date"] < asof}
        if best["date"] < asof:
            print(f"  ⚠️ {key} index stale: {best['date']} < stocks asof {asof}")
    return market


def build(out_dir=None, kis=None, flows_path=None, sleep=time.sleep, log=print):
    """가격·수급을 모아 JSON 3종을 쓴다. 반환: 요약 dict."""
    out = out_dir or OUT
    stocks, fails = {}, []
    for code, en, kr, sec in TICKERS:
        try:
            m = compute(read_prices(code))
        except Exception as e:
            fails.append((code, repr(e)))
            continue
        for field, expect, actual, _tol in inconsistencies(m):
            log(f"  ⚠️ {code} {field} inconsistent: base says {expect}, stored {actual}")
        m.update(name_en=en, name_kr=kr, sector=sec, flow=None)
        stocks[code] = m
        sleep(0.3)
    if len(stocks) < 20:
        runstatus.record("export", "failed", reason=f"only {len(stocks)}/{len(TICKERS)} fetched",
                         extra={"fails": fails})
        raise SystemExit(f"export aborted: only {len(stocks)}/{len(TICKERS)} fetched; fails={fails}")

    asof = max(s["date"] for s in stocks.values())
    stale = sorted(c for c, s in stocks.items() if s["date"] < asof)
    if stale:
        log(f"  ⚠️ {len(stale)} stock(s) behind asof {asof}: {stale}")

    flows_store = load_flows(flows_path) if flows_path else load_flows()
    flow, flow_status = collect_flows(flows_store, {c: s["date"] for c, s in stocks.items()},
                                      kis=kis, log=log)
    for code, s in stocks.items():
        s["flow"] = flow.get(code)
        s["stale"] = s["date"] < asof

    sectors = _sector_summary(stocks)
    market = _market(asof)

    os.makedirs(out, exist_ok=True)
    payloads = (
        ("stocks", {"asof": asof, "flow_status": flow_status, "stocks": stocks}),
        ("sectors", {"asof": asof, "sectors": sectors}),
        ("market", {"asof": asof, **market}),
    )
    for name, payload in payloads:
        with open(os.path.join(out, f"{name}.json"), "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)

    runstatus.record("export", "ok",
                     reason=None if not fails else f"{len(fails)} price failures",
                     extra={"asof": asof, "stocks": len(stocks), "fails": fails})
    runstatus.record("export_flows", "ok" if flow_status["status"] == "ok" else "failed",
                     reason=flow_status["reason"],
                     extra={k: flow_status[k] for k in ("status", "covered", "total", "sources")})
    log(f"export OK asof={asof} stocks={len(stocks)} fails={fails} "
        f"flow={flow_status['status']} {flow_status['covered']}/{flow_status['total']}")
    return {"asof": asof, "stocks": len(stocks), "fails": fails,
            "flow_status": flow_status, "stale": stale}


def run():
    return build(kis=KISFlow())


if __name__ == "__main__":
    run()
