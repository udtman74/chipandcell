"""외국인·기관·개인 수급 일별 이력 축적.

KIS inquire-investor는 30거래일치를 반환한다(2026-08-31 실측: rows=30).
기존 kis_api.get_investor_trend()는 최신 1건만 쓰므로 여기서 직접 호출한다.
수급은 소급 조회가 불가능하므로 매일 받아 append 하는 것이 유일한 확보 수단이다.
"""
import json
import os
import sys
import time
from datetime import datetime

from pipeline.tickers import TICKERS

_DIR = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(_DIR, "..", "site", "src", "data", "history", "flows.json")


def load():
    try:
        with open(STORE) as f:
            return json.load(f)
    except Exception:
        return {"updated": "", "flows": {}}


def save(store, today):
    store["updated"] = today
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w") as f:
        json.dump(store, f, ensure_ascii=False, indent=1, sort_keys=True)


def merge(store, code, rows):
    """rows=[{"date":"YYYYMMDD","f","i","p"}] 병합. 신규 추가 건수 반환(멱등)."""
    per = store.setdefault("flows", {}).setdefault(code, {})
    added = 0
    for r in rows:
        d = r["date"]
        if not d or len(d) != 8:
            continue
        key = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        val = {"f": r["f"], "i": r["i"], "p": r["p"]}
        if per.get(key) != val:
            added += 0 if key in per else 1
            per[key] = val
    return added


def flow5(store, code, date):
    """date 포함 직전 5거래일 외국인·기관 누적. 5일 미만이면 (None, None)."""
    per = store.get("flows", {}).get(code, {})
    days = sorted(d for d in per if d <= date)
    if len(days) < 5:
        return None, None
    last5 = days[-5:]
    return (sum(per[d]["f"] for d in last5), sum(per[d]["i"] for d in last5))


def _screener_path():
    p = os.path.expanduser("~/kr-stock-screener")
    if p not in sys.path:
        sys.path.insert(0, p)
    return p


def _fetch(code, token):
    """KIS 30행 조회 → rows. 실패 시 []."""
    import requests
    _screener_path()
    from kis_api import _headers, KIS_BASE_URL
    url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor"
    try:
        r = requests.get(url, params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
                         headers=_headers(token, "FHKST01010900"), timeout=10)
        if r.status_code != 200:
            return []
    except Exception:
        return []

    def _int(v):
        return int(v) if v and str(v).strip() else 0

    out = []
    for it in r.json().get("output", []):
        out.append({"date": it.get("stck_bsop_date", ""),
                    "f": _int(it.get("frgn_ntby_qty")),
                    "i": _int(it.get("orgn_ntby_qty")),
                    "p": _int(it.get("prsn_ntby_qty"))})
    return out


def run():
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        _screener_path()
        from kis_api import get_access_token
        token = get_access_token()
    except Exception:
        token = None
    if not token:
        print("flow_history skip: KIS token unavailable")
        return
    store = load()
    total = 0
    for code, _en, _kr, _sec in TICKERS:
        total += merge(store, code, _fetch(code, token))
        time.sleep(0.3)
    save(store, today)
    print(f"flow_history OK +{total} rows, codes={len(store['flows'])}")


if __name__ == "__main__":
    run()
