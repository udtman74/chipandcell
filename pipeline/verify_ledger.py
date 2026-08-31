"""사후검증: 기록일로부터 20거래일이 지난 레코드에 실제 결과를 채운다.

거래일 캘린더를 따로 두지 않고 가격 시계열의 거래일을 세어 휴장일을 자동 처리한다.
결과는 유리하든 불리하든 그대로 기록한다(선별 표시·사후 삭제 금지).
"""
from datetime import datetime

import FinanceDataReader as fdr

from pipeline.record_ledger import load, save

HORIZON = 20


def pick_forward(closes, date, horizon=HORIZON):
    """closes=[(date_str, close)] 오름차순. date 이후 horizon번째 거래일 (date, close)."""
    after = [(d, c) for d, c in closes if d > date]
    if len(after) < horizon:
        return None
    return after[horizon - 1]


def run(horizon=HORIZON):
    ledger = load()
    pending = [r for r in ledger["records"] if r.get("verified") is None]
    if not pending:
        print("verify_ledger: nothing pending")
        return
    filled = 0
    for code in sorted({r["code"] for r in pending}):
        try:
            df = fdr.DataReader(code).dropna(subset=["Close"])
        except Exception as e:
            print(f"  ⚠️ {code} price fetch failed: {e!r}")
            continue
        closes = [(d.strftime("%Y-%m-%d"), float(c)) for d, c in zip(df.index, df["Close"])]
        for r in (x for x in pending if x["code"] == code):
            hit = pick_forward(closes, r["date"], horizon)
            if not hit:
                continue
            d, c = hit
            r["verified"] = {"date": d, "close": c, "trading_days": horizon,
                             "return_pct": round((c / r["close"] - 1) * 100, 2)}
            filled += 1
    save(ledger, datetime.now().strftime("%Y-%m-%d"))
    print(f"verify_ledger OK filled={filled}, pending={len(pending) - filled}")


if __name__ == "__main__":
    run()
