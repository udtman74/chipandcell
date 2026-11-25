"""테스트 공용 도우미: 합성 가격 프레임 · 발행 파일 픽스처.

실제 fdr/KIS/LLM 네트워크는 테스트에서 쓰지 않는다. 모두 주입 또는 합성 데이터로 검증한다.
"""
import json
import os
from datetime import date, timedelta

import pandas as pd

from pipeline.metrics import compute
from pipeline.tickers import SECTOR_LABELS, TICKERS

ASOF = "2026-11-13"          # 금요일(거래일) — 주간 리뷰 검사 대상


def frame(closes, start="2026-05-01", volume=1000):
    """종가 리스트 → fdr 형식 DataFrame(영업일 인덱스)."""
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Close": [float(c) for c in closes],
                         "Volume": [volume] * len(closes),
                         "Open": [float(c) for c in closes],
                         "High": [float(c) for c in closes],
                         "Low": [float(c) for c in closes]}, index=idx)


def trading_days(n, end=ASOF):
    """end까지의 영업일 n개(오름차순)."""
    d = date.fromisoformat(end)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return sorted(out)


def price_frames(days=61, end=ASOF):
    """종목·지수별 합성 가격 프레임. 종목마다 다른 추세(부호 섞음)."""
    dates = trading_days(days, end)
    frames = {}
    for i, (code, *_rest) in enumerate(TICKERS):
        step = 1 if i % 3 else -1
        frames[code] = frame([20000 + i * 300 + step * 5 * k for k in range(days)],
                             start=dates[0])
    frames["KS11"] = frame([300 + 0.5 * k for k in range(days)], start=dates[0])
    frames["^KS11"] = frames["KS11"]
    frames["KQ11"] = frame([90 + 0.2 * k for k in range(days)], start=dates[0])
    frames["^KQ11"] = frames["KQ11"]
    return frames


def stocks_doc(frames=None, asof=ASOF, flow=True):
    """compute()로 만든 지표로 stocks.json 페이로드(자기 일관성 보장)를 만든다."""
    frames = frames or price_frames(end=asof)
    stocks = {}
    for code, en, kr, sec in TICKERS:
        m = compute(frames[code])
        m.update(name_en=en, name_kr=kr, sector=sec, stale=False,
                 flow=(({"foreign_net": 10, "inst_net": -10, "individual_net": 0,
                         "date": m["date"], "source": "flows.json"}) if flow else None))
        stocks[code] = m
    return {"asof": asof, "stocks": stocks,
            "flow_status": {"status": "ok" if flow else "failed", "covered": 27 if flow else 0,
                            "total": 27, "sources": {}, "reason": None if flow else "test"}}


def sectors_doc(doc=None):
    doc = doc or stocks_doc()
    stocks = doc["stocks"]
    sectors = {}
    for sec, label in SECTOR_LABELS.items():
        rows = {c: s for c, s in stocks.items() if s["sector"] == sec and s["r20"] is not None}
        rank = sorted(rows, key=lambda c: rows[c]["r20"], reverse=True)
        med = sorted(r["r20"] for r in rows.values())[len(rows) // 2]
        sectors[sec] = {"label": label, "median_r20": round(med, 2),
                        "advancers": sum(1 for r in rows.values() if r["pct"] > 0),
                        "decliners": sum(1 for r in rows.values() if r["pct"] < 0),
                        "top": rank[:3], "bottom": rank[-3:]}
    return {"asof": doc["asof"], "sectors": sectors}


def market_doc(asof=ASOF):
    return {"asof": asof,
            "kospi": {"close": 3000.0, "pct": 0.5, "r20": 1.2, "date": asof, "stale": False},
            "kosdaq": {"close": 900.0, "pct": -0.2, "r20": -0.7, "date": asof, "stale": False}}


def ledger_doc(stocks, days=25, end=ASOF):
    """장부: 종목별 최근 days 영업일 종가. 기준일 종가는 stocks의 bases 값을 그대로 쓴다.

    중간 날짜는 이웃 값으로 채운다(검사는 기준일·직전일 종가만 본다).
    """
    dates = trading_days(days, end=end)
    records = []
    for code, s in stocks.items():
        bases = s.get("bases") or {}
        known = {s["date"]: s["close"]}
        for field in ("pct", "r5", "r20", "r60"):
            b = bases.get(field)
            if b and b.get("date"):
                known[b["date"]] = b["close"]
        known_items = sorted(known.items())
        per = {}
        for d in dates:
            past = [c for k, c in known_items if k <= d]
            per[d] = past[-1] if past else known_items[0][1]
        for d in dates:
            per_date = per[d]
            # pct/r5/r20 기준일은 정확히 장부 값으로 고정한다(검사 대상).
            for field in ("pct", "r5", "r20"):
                b = bases.get(field)
                if b and b.get("date") == d:
                    per_date = b["close"]
            records.append({"code": code, "date": d, "close": per_date, "r20": None,
                            "backfilled": False, "note": None, "verified": None})
    return {"updated": dates[-1], "records": records}


def flows_doc(stocks, dates, value=10):
    return {"updated": dates[-1],
            "flows": {code: {d: {"f": value, "i": -value, "p": 0} for d in dates}
                      for code in stocks}}


def write_fixture(tmp_path, posts_days=None, weekly_dates=None, flow=True,
                  asof=ASOF, extra_posts=()):
    """data/ + posts/ 픽스처. 반환 (data_dir, posts_dir, stocks_doc)."""
    data_dir = tmp_path / "data"
    posts_dir = tmp_path / "posts"
    (data_dir / "history").mkdir(parents=True, exist_ok=True)
    posts_dir.mkdir(parents=True, exist_ok=True)
    doc = stocks_doc(asof=asof, flow=flow)
    dates = trading_days(25, end=asof)
    (data_dir / "stocks.json").write_text(json.dumps(doc, ensure_ascii=False))
    (data_dir / "sectors.json").write_text(json.dumps(sectors_doc(doc), ensure_ascii=False))
    (data_dir / "market.json").write_text(json.dumps(market_doc(asof), ensure_ascii=False))
    (data_dir / "history" / "ledger.json").write_text(
        json.dumps(ledger_doc(doc["stocks"], end=asof), ensure_ascii=False))
    (data_dir / "history" / "flows.json").write_text(
        json.dumps(flows_doc(doc["stocks"], dates[-3:]), ensure_ascii=False))
    for d in (posts_days if posts_days is not None else dates[-5:]):
        (posts_dir / f"{d}-deep-dive.md").write_text("---\ntitle: x\n---\n")
    for d in (weekly_dates if weekly_dates is not None else []):
        (posts_dir / f"{d}-weekly-review.md").write_text("---\ntitle: x\n---\n")
    for name in extra_posts:
        (posts_dir / name).write_text("---\ntitle: x\n---\n")
    return data_dir, posts_dir, doc


def read(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
