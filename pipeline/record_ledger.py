"""관찰 장부: 매일 27종목 구조화 스냅샷을 누적한다(예측 아님, 사실 기록).

최초 실행 시 수급 이력과 같은 구간(기본 30거래일)을 백필하되,
백필 레코드의 지표는 그 날짜 기준으로 계산하고 backfilled=True로 표시한다.
백필 레코드는 커밋 시점이 관찰 시점보다 늦어 git 증명을 갖지 못하며,
그것이 backfilled 표기가 필요한 이유다.
"""
import json
import os
from datetime import datetime

import FinanceDataReader as fdr

from pipeline.tickers import TICKERS
from pipeline.metrics import compute
from pipeline.flow_history import load as load_flows, flow5

_DIR = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(_DIR, "..", "site", "src", "data", "history", "ledger.json")


def load():
    try:
        with open(STORE) as f:
            return json.load(f)
    except Exception:
        return {"updated": "", "records": []}


def save(ledger, today):
    ledger["updated"] = today
    ledger["records"].sort(key=lambda r: (r["date"], r["code"]))
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=1)


def snapshot(code, m, store, date, backfilled):
    f5, i5 = flow5(store, code, date)
    return {
        "code": code,
        "date": date,
        "close": m["close"],
        "pos52": m["pos52"],
        "vs_ma20": round((m["close"] / m["ma20"] - 1) * 100, 2) if m["ma20"] else None,
        "vs_ma60": round((m["close"] / m["ma60"] - 1) * 100, 2) if m["ma60"] else None,
        "r20": round(m["r20"], 2) if m["r20"] is not None else None,
        "flow5_f": f5,
        "flow5_i": i5,
        "backfilled": backfilled,
        "note": None,
        "note_post": None,
        "verified": None,
    }


def append(ledger, rec):
    key = (rec["code"], rec["date"])
    if any((r["code"], r["date"]) == key for r in ledger["records"]):
        return False
    ledger["records"].append(rec)
    return True


def attach_note(ledger, code, date, note, post_slug):
    for r in ledger["records"]:
        if r["code"] == code and r["date"] == date:
            r["note"] = note
            r["note_post"] = post_slug
            return True
    return False


def run(backfill_days=30):
    today = datetime.now().strftime("%Y-%m-%d")
    flows = load_flows()
    ledger = load()
    first_run = ledger["updated"] == ""
    added = 0
    for code, _en, _kr, _sec in TICKERS:
        try:
            df = fdr.DataReader(code)
        except Exception as e:
            print(f"  ⚠️ {code} price fetch failed: {e!r}")
            continue
        dates = [d.strftime("%Y-%m-%d") for d in df.index[-backfill_days:]]
        for d in dates:
            m = compute(df, asof=d)
            # 최신 봉을 당일 정규 실행으로 기록할 때만 실시간 관찰이다.
            is_backfill = first_run or d != dates[-1]
            if append(ledger, snapshot(code, m, flows, d, backfilled=is_backfill)):
                added += 1
    save(ledger, today)
    print(f"record_ledger OK +{added} records, total={len(ledger['records'])}")


if __name__ == "__main__":
    run()
