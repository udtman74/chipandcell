"""일일 데이터 export: fdr(시세)+kis_api(수급, 미니에서만) → site/src/data/*.json"""
import json
import os
import sys
import time

import FinanceDataReader as fdr

from pipeline.tickers import TICKERS, SECTOR_LABELS
from pipeline.metrics import compute

OUT = os.path.join(os.path.dirname(__file__), "..", "site", "src", "data")


def _flow(code):
    """외인/기관 수급. kr-screener kis_api가 있는 머신(미니)에서만 동작, 실패 시 None."""
    try:
        p = os.path.expanduser("~/kr-stock-screener")
        if p not in sys.path:
            sys.path.insert(0, p)
        from kis_api import get_access_token, get_investor_trend
        token = get_access_token()
        inv = get_investor_trend(code, token) if token else {}
        out = {k: inv[k] for k in ("foreign_net", "inst_net", "individual_net") if k in inv}
        return out or None
    except Exception:
        return None


def run():
    stocks, fails = {}, []
    for code, en, kr, sec in TICKERS:
        try:
            m = compute(fdr.DataReader(code))
            m.update(name_en=en, name_kr=kr, sector=sec, flow=_flow(code))
            stocks[code] = m
            time.sleep(0.3)
        except Exception as e:
            fails.append((code, repr(e)))
    if len(stocks) < 20:
        raise SystemExit(f"export aborted: only {len(stocks)}/27 fetched; fails={fails}")
    asof = max(s["date"] for s in stocks.values())
    sectors = {}
    for sec, label in SECTOR_LABELS.items():
        rows = {c: s for c, s in stocks.items() if s["sector"] == sec and s["r20"] is not None}
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
    market = {}
    # KS11/KQ11(네이버 경로)은 미니에서 빈 DF를 반환하는 사례가 있어 야후(^) 폴백
    for key, syms in (("kospi", ("KS11", "^KS11")), ("kosdaq", ("KQ11", "^KQ11"))):
        for sym in syms:
            df = fdr.DataReader(sym)
            if len(df) and "Close" in df.columns:
                m = compute(df)
                market[key] = {"close": m["close"], "pct": m["pct"], "r20": m["r20"]}
                break
        else:
            raise SystemExit(f"export aborted: index fetch failed for {key} ({syms})")
    os.makedirs(OUT, exist_ok=True)
    for name, payload in (("stocks", {"asof": asof, "stocks": stocks}),
                          ("sectors", {"asof": asof, "sectors": sectors}),
                          ("market", {"asof": asof, **market})):
        with open(os.path.join(OUT, f"{name}.json"), "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"export OK asof={asof} stocks={len(stocks)} fails={fails}")


if __name__ == "__main__":
    run()
