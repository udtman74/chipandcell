# Chip & Cell 시각화·고유 데이터 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수급 시계열·관찰 장부를 축적하고, 캔들·수급·로테이션 차트와 밸류체인 계층도, 사후검증된 종목별 기록을 사이트에 노출한다.

**Architecture:** 별도 DB 없이 리포 내 JSON(`site/src/data/history/`)에 데이터를 누적하고, 파이프라인이 빌드 전에 인라인 SVG 파일(`site/src/data/charts/`)을 생성하며, Astro가 `import.meta.glob`으로 이를 읽어 페이지에 삽입한다. 순수 함수(지표 as-of 계산, 5일 누적, D+20 선택, SVG 생성)와 I/O(파일·API)를 분리해 네트워크 없이 단위 테스트한다.

**Tech Stack:** Python 3(FinanceDataReader, pandas, requests), Astro 5, 인라인 SVG(라이브러리 없음), launchd, Vercel.

**Spec:** `docs/superpowers/specs/2026-09-01-visual-and-proprietary-data-design.md`

## Global Constraints

- 사이트 표기는 전부 영어. 모든 페이지 푸터 고지 유지: "Not investment advice. Data may contain errors."
- 커밋 author: `udtman74 <260236632+udtman74@users.noreply.github.com>` (리포 git config로 이미 고정).
- **예측·목표가·매수/매도 언어 금지.** 장부는 "관찰의 기록"이며 "콜"이 아니다.
- **백필과 실시간 관찰을 구분한다.** 백필 레코드는 `backfilled: true`, 화면에도 소급 계산임을 명시. LLM 노트는 오늘 이후 생성분만 존재.
- **검증 결과는 유리하든 불리하든 그대로 표시한다.** 선별 표시·사후 삭제 금지.
- **밸류체인 관계선은 출처 URL과 연도가 확인된 것만 포함한다.** 확인 못 하면 넣지 않는다.
- **차트에도 스테일 가드 적용**: 데이터가 최신이 아니면 차트를 생성하지 않는다(페이지는 해당 영역을 생략).
- 신규 URL 추가 금지(기존 페이지에 얹는다). 자바스크립트 차트 라이브러리 금지. 회사 로고 금지.
- 로그는 전량 보존(`/dev/null` 금지). 실패 시 텔레그램 발송 금지 — 로그만.
- 모든 fact(종목코드·회사명·공급관계)는 도구로 조회해 검증한다. 추정 금지.
- 작업 완료 시 실제 실행으로 실증한다(파이프라인 실행 + 라이브 URL 확인).
- 테스트 실행: `cd ~/chipandcell && .venv/bin/python -m pytest pipeline/tests -q`

---

## Phase 1 — 데이터 축적 (시간 임계: 오늘 착수)

### Task 1: `metrics.compute`에 as-of 계산 추가

과거 시점 스냅샷을 만들려면 그 날짜까지만 잘라 계산해야 한다. 오늘 값을 과거 레코드에 넣으면 미래 정보 누출이자 사실 오류다.

**Files:**
- Modify: `pipeline/metrics.py`
- Test: `pipeline/tests/test_metrics.py`

**Interfaces:**
- Produces: `compute(df, asof=None) -> dict` — 기존 반환 키 불변(`close,pct,value_bil,hi52,lo52,pos52,ma20,ma60,r5,r20,r60,date`). `asof`(`"YYYY-MM-DD"`) 지정 시 그 일자까지만 사용.

- [ ] **Step 1: 실패하는 테스트 작성** (`pipeline/tests/test_metrics.py`에 추가)

```python
def test_compute_asof_slices_series():
    df = _df(list(range(100, 400)))          # 2025-01-01부터 300 영업일, 단조 상승
    asof = df.index[199].strftime("%Y-%m-%d")
    m = compute(df, asof=asof)
    assert m["close"] == 299                  # 200번째 봉 종가
    assert m["date"] == asof

def test_compute_asof_none_uses_full_series():
    df = _df(list(range(100, 400)))
    assert compute(df)["close"] == 399
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest pipeline/tests/test_metrics.py -q`
Expected: FAIL — `compute() got an unexpected keyword argument 'asof'`

- [ ] **Step 3: 구현** — `pipeline/metrics.py` 상단에 `import pandas as pd`를 추가하고 함수 시그니처와 첫 두 줄을 교체:

```python
import pandas as pd


def compute(df, asof=None):
    """OHLCV DataFrame(fdr 형식) → 지표 dict. 52주=252거래일 근사.

    asof: "YYYY-MM-DD". 지정 시 그 일자까지만 사용(과거 시점 재현용).
    """
    df = df.dropna(subset=["Close"])
    if asof is not None:
        df = df[df.index <= pd.Timestamp(asof)]
    df = df.tail(300)
    c = df["Close"]
```

이후 본문은 변경하지 않는다.

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `.venv/bin/python -m pytest pipeline/tests -q`
Expected: PASS (기존 테스트 포함 전건)

- [ ] **Step 5: 커밋**

```bash
git add pipeline/metrics.py pipeline/tests/test_metrics.py
git commit -m "feat: metrics.compute asof 옵션(과거 시점 지표 재현)"
```

---

### Task 2: 수급 이력 축적 (`flow_history.py`)

KIS API가 30거래일치를 반환하는데 기존 래퍼는 최신 1건만 쓰고 버린다. 이 30일은 **지금 받지 않으면 영구히 사라진다.**

**Files:**
- Create: `pipeline/flow_history.py`, `pipeline/tests/test_flow_history.py`
- Data: `site/src/data/history/flows.json`

**Interfaces:**
- Consumes: `pipeline.tickers.TICKERS`
- Produces:
  - `load() -> dict` — `{"updated": "YYYY-MM-DD", "flows": {code: {"YYYY-MM-DD": {"f": int, "i": int, "p": int}}}}`. 파일 없으면 빈 구조.
  - `merge(store, code, rows) -> int` — `rows`=`[{"date":"YYYYMMDD","f":int,"i":int,"p":int}]`를 병합, 신규 추가 건수 반환(멱등).
  - `flow5(store, code, date) -> tuple[int|None, int|None]` — `date` 포함 직전 5거래일 외국인·기관 누적. 5일 미만이면 `(None, None)`.
  - `run() -> None` — CLI `python3 -m pipeline.flow_history`. KIS 실패 시 no-op 로그 후 정상 종료(배치 중단 금지).

- [ ] **Step 1: 실패하는 테스트 작성** (`pipeline/tests/test_flow_history.py`)

```python
from pipeline.flow_history import merge, flow5


def _store():
    return {"updated": "2026-09-01", "flows": {}}


def test_merge_adds_and_is_idempotent():
    st = _store()
    rows = [{"date": "20260831", "f": 10, "i": -5, "p": -5},
            {"date": "20260828", "f": 1, "i": 2, "p": -3}]
    assert merge(st, "005930", rows) == 2
    assert merge(st, "005930", rows) == 0          # 재실행 시 중복 없음
    assert st["flows"]["005930"]["2026-08-31"] == {"f": 10, "i": -5, "p": -5}


def test_flow5_sums_last_five_sessions():
    st = _store()
    rows = [{"date": f"2026081{d}", "f": 1, "i": 10, "p": 0} for d in range(1, 7)]
    merge(st, "000660", rows)
    f, i = flow5(st, "000660", "2026-08-16")
    assert (f, i) == (5, 50)                        # 8/12~8/16 5거래일


def test_flow5_returns_none_when_insufficient():
    st = _store()
    merge(st, "000660", [{"date": "20260811", "f": 1, "i": 1, "p": 0}])
    assert flow5(st, "000660", "2026-08-11") == (None, None)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest pipeline/tests/test_flow_history.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.flow_history'`

- [ ] **Step 3: 구현** (`pipeline/flow_history.py`)

```python
"""외국인·기관·개인 수급 일별 이력 축적.

KIS inquire-investor는 30거래일치를 반환한다(2026-08-31 실측: rows=30).
기존 kis_api.get_investor_trend()는 최신 1건만 쓰므로 여기서 직접 호출한다.
수급은 소급 조회가 불가능하므로 매일 받아 append 하는 것이 유일한 확보 수단이다.
"""
import json
import os
import sys
import time

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


def _fetch(code, token):
    """KIS 30행 조회 → rows. 실패 시 []."""
    import requests
    p = os.path.expanduser("~/kr-stock-screener")
    if p not in sys.path:
        sys.path.insert(0, p)
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
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        p = os.path.expanduser("~/kr-stock-screener")
        if p not in sys.path:
            sys.path.insert(0, p)
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: 미니에서 실제 백필 실증** — KIS 토큰이 미니에만 있으므로 미니에서 실행한다.

```bash
ssh shinminim4@192.168.10.1 'cd ~/chipandcell && git pull -q --rebase && .venv/bin/python -m pipeline.flow_history && .venv/bin/python -c "
import json; d=json.load(open(\"site/src/data/history/flows.json\"))
c=d[\"flows\"][\"005930\"]; print(\"005930 days:\", len(c), min(c), max(c))
print(\"codes:\", len(d[\"flows\"]))"'
```
Expected: `flow_history OK +약 800 rows`, `005930 days: 30`, `codes: 27`

- [ ] **Step 6: 커밋** (미니에서 생성된 데이터를 에어로 가져와 함께 커밋)

```bash
git add pipeline/flow_history.py pipeline/tests/test_flow_history.py site/src/data/history/flows.json
git commit -m "feat: 수급 30거래일 이력 백필+일일 축적"
```

---

### Task 3: 관찰 장부 (`record_ledger.py`)

**Files:**
- Create: `pipeline/record_ledger.py`, `pipeline/tests/test_record_ledger.py`
- Data: `site/src/data/history/ledger.json`

**Interfaces:**
- Consumes: `pipeline.metrics.compute(df, asof=)`, `pipeline.flow_history.load/flow5`, `pipeline.tickers.TICKERS`
- Produces:
  - `snapshot(code, m, store, date, backfilled) -> dict` — 레코드 1건. 키: `code,date,close,pos52,vs_ma20,vs_ma60,r20,flow5_f,flow5_i,backfilled,note,note_post,verified`
  - `append(ledger, rec) -> bool` — (code,date) 중복이면 `False`(멱등), 추가되면 `True`
  - `load() -> dict` / `save(ledger, today)` — `{"updated": str, "records": [...]}`
  - `attach_note(ledger, code, date, note, post_slug) -> bool` — 해당 레코드에 LLM 관찰 노트 기입
  - `run(backfill_days=30) -> None` — CLI `python3 -m pipeline.record_ledger`

- [ ] **Step 1: 실패하는 테스트 작성** (`pipeline/tests/test_record_ledger.py`)

```python
from pipeline.record_ledger import snapshot, append, attach_note

M = {"close": 100.0, "pos52": 50.0, "ma20": 80.0, "ma60": 125.0, "r20": 12.345}
STORE = {"flows": {"005930": {f"2026-08-2{d}": {"f": 2, "i": -1, "p": -1} for d in range(1, 7)}}}


def test_snapshot_fields():
    r = snapshot("005930", M, STORE, "2026-08-26", backfilled=True)
    assert r["code"] == "005930" and r["date"] == "2026-08-26"
    assert r["vs_ma20"] == 25.0 and r["vs_ma60"] == -20.0
    assert r["flow5_f"] == 10 and r["flow5_i"] == -5
    assert r["backfilled"] is True
    assert r["note"] is None and r["verified"] is None


def test_snapshot_flow_none_when_insufficient_history():
    r = snapshot("000660", M, STORE, "2026-08-26", backfilled=False)
    assert r["flow5_f"] is None and r["flow5_i"] is None


def test_append_is_idempotent():
    led = {"updated": "", "records": []}
    r = snapshot("005930", M, STORE, "2026-08-26", backfilled=False)
    assert append(led, r) is True
    assert append(led, dict(r)) is False
    assert len(led["records"]) == 1


def test_attach_note_sets_note_and_post():
    led = {"updated": "", "records": [snapshot("005930", M, STORE, "2026-08-26", False)]}
    assert attach_note(led, "005930", "2026-08-26", "Foreign selling persisted.", "2026-08-26-samsung") is True
    assert led["records"][0]["note_post"] == "2026-08-26-samsung"
    assert attach_note(led, "005930", "2026-01-01", "x", "y") is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest pipeline/tests/test_record_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.record_ledger'`

- [ ] **Step 3: 구현** (`pipeline/record_ledger.py`)

```python
"""관찰 장부: 매일 27종목 구조화 스냅샷을 누적한다(예측 아님, 사실 기록).

최초 실행 시 수급 이력과 같은 구간(기본 30거래일)을 백필하되,
백필 레코드의 지표는 그 날짜 기준으로 계산하고 backfilled=True로 표시한다.
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
            is_backfill = d != dates[-1] or ledger["updated"] == ""
            if append(ledger, snapshot(code, m, flows, d, backfilled=is_backfill)):
                added += 1
    save(ledger, today)
    print(f"record_ledger OK +{added} records, total={len(ledger['records'])}")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add pipeline/record_ledger.py pipeline/tests/test_record_ledger.py
git commit -m "feat: 관찰 장부 스냅샷 축적(30일 백필, as-of 계산)"
```

---

### Task 4: 사후검증 (`verify_ledger.py`)

**Files:**
- Create: `pipeline/verify_ledger.py`, `pipeline/tests/test_verify_ledger.py`

**Interfaces:**
- Consumes: `pipeline.record_ledger.load/save`
- Produces:
  - `pick_forward(closes, date, horizon=20) -> tuple[str, float] | None` — `closes`=`[(date_str, close)]` 오름차순. `date` **이후** 거래일이 `horizon` 미만이면 `None`, 아니면 `horizon`번째 거래일의 `(date, close)`.
  - `run(horizon=20) -> None` — CLI `python3 -m pipeline.verify_ledger`

- [ ] **Step 1: 실패하는 테스트 작성** (`pipeline/tests/test_verify_ledger.py`)

```python
from pipeline.verify_ledger import pick_forward

CLOSES = [(f"2026-08-{d:02d}", 100.0 + d) for d in range(1, 21)]  # 8/01~8/20


def test_pick_forward_selects_nth_trading_day_after():
    assert pick_forward(CLOSES, "2026-08-05", horizon=3) == ("2026-08-08", 108.0)


def test_pick_forward_none_when_horizon_not_reached():
    assert pick_forward(CLOSES, "2026-08-19", horizon=3) is None


def test_pick_forward_ignores_same_day():
    assert pick_forward(CLOSES, "2026-08-01", horizon=1) == ("2026-08-02", 102.0)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest pipeline/tests/test_verify_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.verify_ledger'`

- [ ] **Step 3: 구현** (`pipeline/verify_ledger.py`)

```python
"""사후검증: 기록일로부터 20거래일이 지난 레코드에 실제 결과를 채운다.

거래일 캘린더를 따로 두지 않고 가격 시계열의 거래일을 세어 휴장일을 자동 처리한다.
결과는 유리하든 불리하든 그대로 기록한다(선별 표시·삭제 금지).
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add pipeline/verify_ledger.py pipeline/tests/test_verify_ledger.py
git commit -m "feat: D+20 사후검증(거래일 세기, 결과 무조건 기록)"
```

---

### Task 5: 파이프라인 통합 + LLM 노트 축적 + 라이브 실증

노트도 소급 불가 자산이므로 UI보다 먼저 쌓기 시작한다.

**Files:**
- Modify: `pipeline/run_daily.sh`, `pipeline/gen_deep_dive.py`

**Interfaces:**
- Consumes: `pipeline.record_ledger.{load,save,attach_note}`, `pipeline.llm.analyze`
- Produces: 심층 글 생성 시 해당 (code, 데이터 일자) 레코드에 `note`(1~3문장)와 `note_post`(slug) 기입

- [ ] **Step 1: `gen_deep_dive.py`에 노트 기입 추가** — `run()`에서 글 파일을 쓴 직후, `_save_state(state)` 앞에 삽입:

```python
    # 관찰 노트를 장부에 기록(소급 불가 자산 — UI보다 먼저 축적)
    try:
        from pipeline.record_ledger import load as load_ledger, save as save_ledger, attach_note
        note = analyze(
            "From the analyst note below, extract the 2-3 sentence factual observation that "
            "would matter when reviewing this stock 20 trading days from now. "
            "State only what was observed (levels, flows, position in range) — no prediction, "
            "no recommendation, no price target. Plain text, no markdown.\n\n" + analysis)
        if note:
            led = load_ledger()
            slug = os.path.basename(out)[:-3]
            if attach_note(led, code, s["date"], note.strip(), slug):
                save_ledger(led, today)
                print(f"  📝 ledger note attached: {code} {s['date']}")
    except Exception as e:
        print(f"  ⚠️ ledger note skipped: {e!r}")
```

- [ ] **Step 2: `run_daily.sh` 순서 확장** — `python3 -m pipeline.export_data` 줄 다음, `gen_deep_dive` 줄 앞에 삽입. 신규 단계는 실패해도 후속을 막지 않는다(`|| echo`).

```bash
  "$PY" -m pipeline.flow_history || echo "FLOW_HISTORY FAILED (continuing)"
  "$PY" -m pipeline.record_ledger || echo "RECORD_LEDGER FAILED (continuing)"
  "$PY" -m pipeline.verify_ledger || echo "VERIFY_LEDGER FAILED (continuing)"
```

- [ ] **Step 3: `git add` 대상에 history 추가** — `run_daily.sh`의 `git add` 줄을 교체:

```bash
  git add site/src/data site/src/content/posts
```

- [ ] **Step 4: 미니에서 전 사이클 라이브 실증**

```bash
ssh shinminim4@192.168.10.1 'cd ~/chipandcell && git pull -q --rebase && \
  launchctl kickstart -k gui/$(id -u)/com.chipandcell.daily'
```
그 후 로그에서 `flow_history OK` → `record_ledger OK` → `verify_ledger OK` → `deep dive OK` → `push` 완주를 확인하고, `ledger.json`에 검증 완료 레코드가 실제로 존재하는지 확인한다:

```bash
ssh shinminim4@192.168.10.1 'cd ~/chipandcell && .venv/bin/python -c "
import json; d=json.load(open(\"site/src/data/history/ledger.json\"))
rs=d[\"records\"]; v=[r for r in rs if r[\"verified\"]]
print(\"records:\", len(rs), \"verified:\", len(v), \"notes:\", sum(1 for r in rs if r[\"note\"]))
print(\"sample:\", v[0] if v else None)"'
```
Expected: `records` 약 800, `verified` 0보다 큼(30일 백필 중 D+20 도달분), `notes` 1 이상

- [ ] **Step 5: 커밋**

```bash
git add pipeline/run_daily.sh pipeline/gen_deep_dive.py site/src/data/history
git commit -m "feat: 일일 배치에 이력·장부·검증 편입 + LLM 관찰 노트 축적"
```

---

## Phase 2 — 차트

### Task 6: 차트 생성기 (`charts.py`)

**Files:**
- Create: `pipeline/charts.py`, `pipeline/tests/test_charts.py`
- Modify: `site/src/layouts/Base.astro` (시리즈 색 토큰 2개 추가)

**Interfaces:**
- Consumes: `pipeline.flow_history.load`
- Produces:
  - `candle_svg(df, title="") -> str` — OHLC DataFrame(오름차순). 10봉 미만이면 `""`.
  - `flow_svg(dates, f_vals, i_vals, title="") -> str` — 누적 순매수 2개 라인. 5일 미만이면 `""`.
  - `scatter_svg(points, title="") -> str` — `points`=`[(label, x, y)]`. 3점 미만이면 `""`.
  - `build_all() -> None` — CLI `python3 -m pipeline.charts`. 산출물 `site/src/data/charts/{code}-candle.svg`, `{code}-flow.svg`, `{sector}-scatter.svg`

**중요 — SVG에서 CSS 변수 사용법:** `fill="var(--up)"` 같은 **표현 속성에서는 `var()`가 해석되지 않는다.** 반드시 `style="fill:var(--up)"` 형태의 인라인 스타일로 써야 한다. 이걸 틀리면 차트가 검게 나오거나 보이지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성** (`pipeline/tests/test_charts.py`)

```python
import pandas as pd

from pipeline.charts import candle_svg, flow_svg, scatter_svg


def _ohlc(n):
    idx = pd.bdate_range("2026-01-01", periods=n)
    return pd.DataFrame({"Open": [100.0] * n, "High": [110.0] * n,
                         "Low": [90.0] * n, "Close": [105.0] * n}, index=idx)


def test_candle_returns_svg_and_uses_css_vars():
    out = candle_svg(_ohlc(60), title="Test")
    assert out.startswith("<svg") and out.rstrip().endswith("</svg>")
    assert "style=\"fill:var(--up)" in out or "style=\"stroke:var(--up)" in out
    assert "fill=\"var(" not in out          # 표현 속성에 var() 쓰면 안 됨


def test_candle_empty_when_too_short():
    assert candle_svg(_ohlc(5)) == ""


def test_flow_svg_empty_when_too_short():
    assert flow_svg(["2026-08-03"], [1], [2]) == ""


def test_flow_svg_renders_two_series():
    dates = [f"2026-08-{d:02d}" for d in range(3, 11)]
    out = flow_svg(dates, [1] * 8, [-1] * 8)
    assert out.count("<polyline") == 2


def test_scatter_empty_when_too_few_points():
    assert scatter_svg([("A", 1.0, 2.0)]) == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest pipeline/tests/test_charts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.charts'`

- [ ] **Step 3: `Base.astro`에 시리즈 색 토큰 추가** — `:root`와 다크 블록 양쪽에 추가한다.

`:root { ... }` 안 마지막 줄에:
```css
    --series-a: #0b5fff; --series-b: #8a6d3b;
```
`@media (prefers-color-scheme: dark) { :root { ... } }` 안 마지막 줄에:
```css
      --series-a: #6ea8ff; --series-b: #d9b56b;
```

- [ ] **Step 4: 구현** (`pipeline/charts.py`) — 색은 전부 인라인 `style`로 CSS 변수를 참조한다.

```python
"""빌드 시점 인라인 SVG 차트. 외부 라이브러리·자바스크립트 없음.

색상은 표현 속성이 아니라 style 인라인으로 CSS 변수를 참조한다
(fill="var(--up)"는 브라우저가 해석하지 않는다).
"""
import json
import os

import FinanceDataReader as fdr

from pipeline.tickers import TICKERS, SECTOR_LABELS
from pipeline.flow_history import load as load_flows

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "..", "site", "src", "data")
OUT = os.path.join(DATA, "charts")
W, H, PAD = 720, 240, 40

_SVG = ('<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="{alt}" style="width:100%;height:auto">{body}</svg>')
_TXT = ('<text x="{x}" y="{y}" font-size="11" style="fill:var(--muted)"{anchor}>{t}</text>')


def _txt(x, y, t, anchor=None, size=11):
    a = f' text-anchor="{anchor}"' if anchor else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" style="fill:var(--muted)"{a}>{t}</text>')


def candle_svg(df, title=""):
    """일봉 캔들. df=OHLC(오름차순). 10봉 미만이면 ""."""
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 10:
        return ""
    lo, hi = float(df["Low"].min()), float(df["High"].max())
    span = (hi - lo) or 1

    def y(p):
        return round(PAD + (hi - p) / span * (H - 2 * PAD), 1)

    n = len(df)
    step = (W - 2 * PAD) / n
    cw = max(2, round(step * 0.6, 1))
    parts = []
    for i, (_, r) in enumerate(df.iterrows()):
        x = round(PAD + i * step + step / 2, 1)
        o, c, h_, l_ = float(r["Open"]), float(r["Close"]), float(r["High"]), float(r["Low"])
        var = "var(--up)" if c >= o else "var(--down)"
        parts.append(f'<line x1="{x}" y1="{y(h_)}" x2="{x}" y2="{y(l_)}" '
                     f'style="stroke:{var}" stroke-width="1"/>')
        top, bot = y(max(o, c)), y(min(o, c))
        parts.append(f'<rect x="{round(x - cw / 2, 1)}" y="{top}" width="{cw}" '
                     f'height="{max(1, round(bot - top, 1))}" style="fill:{var}"/>')
    d0 = df.index[0].strftime("%Y-%m-%d")
    d1 = df.index[-1].strftime("%Y-%m-%d")
    axis = (_txt(PAD, H - 10, d0) + _txt(W - PAD, H - 10, d1, "end")
            + _txt(W - PAD, y(hi) + 10, f"{hi:,.0f}", "end")
            + _txt(W - PAD, y(lo), f"{lo:,.0f}", "end"))
    cap = _txt(PAD, PAD - 16, title, size=12) if title else ""
    return _SVG.format(w=W, h=H, alt=title or "Candlestick chart",
                       body=cap + axis + "".join(parts))


def flow_svg(dates, f_vals, i_vals, title=""):
    """외국인·기관 누적 순매수 2개 라인. 5일 미만이면 ""."""
    if len(dates) < 5:
        return ""
    def _cum(vals):
        out, acc = [], 0
        for v in vals:
            acc += v
            out.append(acc)
        return out
    fc, ic = _cum(f_vals), _cum(i_vals)
    lo = min(min(fc), min(ic), 0)
    hi = max(max(fc), max(ic), 0)
    span = (hi - lo) or 1
    n = len(dates)
    step = (W - 2 * PAD) / max(1, n - 1)

    def y(v):
        return round(PAD + (hi - v) / span * (H - 2 * PAD), 1)

    def line(series, var):
        pts = " ".join(f"{round(PAD + i * step, 1)},{y(v)}" for i, v in enumerate(series))
        return (f'<polyline points="{pts}" fill="none" style="stroke:{var}" stroke-width="2"/>')

    zero = (f'<line x1="{PAD}" y1="{y(0)}" x2="{W - PAD}" y2="{y(0)}" '
            f'style="stroke:var(--line)" stroke-width="1" stroke-dasharray="4,3"/>')
    legend = (_txt(PAD, PAD - 16, "Cumulative net buying — ", size=12)
              + f'<text x="{PAD + 168}" y="{PAD - 16}" font-size="12" '
                f'style="fill:var(--series-a)">Foreign</text>'
              + f'<text x="{PAD + 224}" y="{PAD - 16}" font-size="12" '
                f'style="fill:var(--series-b)">Institutions</text>')
    axis = _txt(PAD, H - 10, dates[0]) + _txt(W - PAD, H - 10, dates[-1], "end")
    return _SVG.format(w=W, h=H, alt=title or "Cumulative investor flows",
                       body=legend + axis + zero
                            + line(fc, "var(--series-a)") + line(ic, "var(--series-b)"))


def scatter_svg(points, title=""):
    """points=[(label, x, y)] 산점도. 3점 미만이면 ""."""
    if len(points) < 3:
        return ""
    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    x0, x1 = min(xs + [0]), max(xs + [0])
    y0, y1 = min(ys + [0]), max(ys + [0])
    xs_span = (x1 - x0) or 1
    ys_span = (y1 - y0) or 1

    def px(v):
        return round(PAD + (v - x0) / xs_span * (W - 2 * PAD), 1)

    def py(v):
        return round(PAD + (y1 - v) / ys_span * (H - 2 * PAD), 1)

    body = [
        f'<line x1="{PAD}" y1="{py(0)}" x2="{W - PAD}" y2="{py(0)}" '
        f'style="stroke:var(--line)" stroke-width="1"/>',
        f'<line x1="{px(0)}" y1="{PAD}" x2="{px(0)}" y2="{H - PAD}" '
        f'style="stroke:var(--line)" stroke-width="1"/>',
        _txt(PAD, PAD - 16, title or "20-day vs 60-day return (%)", size=12),
        _txt(W - PAD, H - 10, "60-day return →", "end"),
    ]
    for label, x, y in points:
        body.append(f'<circle cx="{px(x)}" cy="{py(y)}" r="4" style="fill:var(--series-a)"/>')
        body.append(_txt(px(x) + 6, py(y) - 5, label, size=10))
    return _SVG.format(w=W, h=H, alt=title or "Sector rotation scatter", body="".join(body))


def _write(name, svg):
    if not svg:
        return 0
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(svg)
    return 1


def build_all():
    with open(os.path.join(DATA, "stocks.json")) as f:
        doc = json.load(f)
    stocks, asof = doc["stocks"], doc["asof"]
    flows = load_flows()
    made = 0
    for code, en, _kr, _sec in TICKERS:
        s = stocks.get(code)
        if not s or s["date"] != asof:      # 스테일 가드: 최신이 아니면 그리지 않는다
            continue
        try:
            df = fdr.DataReader(code).tail(60)
        except Exception as e:
            print(f"  ⚠️ {code} chart skipped: {e!r}")
            continue
        made += _write(f"{code}-candle.svg", candle_svg(df, f"{en} — last 60 sessions"))
        per = flows.get("flows", {}).get(code, {})
        days = sorted(per)[-30:]
        made += _write(f"{code}-flow.svg",
                       flow_svg(days, [per[d]["f"] for d in days], [per[d]["i"] for d in days]))
    for sector, label in SECTOR_LABELS.items():
        pts = [(s["name_en"], s["r60"], s["r20"]) for c, s in stocks.items()
               if s["sector"] == sector and s["r20"] is not None and s["r60"] is not None]
        made += _write(f"{sector}-scatter.svg",
                       scatter_svg(pts, f"{label}: 20-day vs 60-day return (%)"))
    print(f"charts OK {made} files")


if __name__ == "__main__":
    build_all()
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 6: 실제 생성 실증**

Run: `.venv/bin/python -m pipeline.charts && ls site/src/data/charts | head && ls site/src/data/charts | wc -l`
Expected: `charts OK ...`, `{code}-candle.svg` 등 파일 생성(종목 27 × 최대 2 + 섹터 2)

- [ ] **Step 7: 커밋**

```bash
git add pipeline/charts.py pipeline/tests/test_charts.py site/src/layouts/Base.astro site/src/data/charts
git commit -m "feat: 인라인 SVG 차트 생성기(캔들·누적수급·로테이션)"
```

---

### Task 7: 차트를 페이지에 삽입

**Files:**
- Modify: `site/src/pages/stocks/[code].astro`, `site/src/components/SectorTable.astro`
- Modify: `pipeline/run_daily.sh` (charts 단계 추가)

**Interfaces:**
- Consumes: `site/src/data/charts/*.svg`

**중요 — Astro에서 동적 파일명 SVG 읽기:** 정적 `import` 경로에는 변수를 넣을 수 없다. `import.meta.glob`을 `eager: true`로 써야 한다. 파일이 없으면 `undefined`가 되고, 그 경우 차트 영역을 렌더하지 않는다(스테일 가드와 동일한 동작).

- [ ] **Step 1: 종목 페이지에 캔들·수급 차트 추가** — `[code].astro` frontmatter 끝(`const title = ...` 앞)에 삽입:

```js
const charts = import.meta.glob("../../data/charts/*.svg", {
  query: "?raw", import: "default", eager: true,
});
const candle = charts[`../../data/charts/${code}-candle.svg`];
const flowChart = charts[`../../data/charts/${code}-flow.svg`];
```

`<h2>Price snapshot</h2>` 표 블록 바로 뒤에 삽입:

```astro
  {candle && (
    <>
      <h2>Price history</h2>
      <figure set:html={candle} />
    </>
  )}
```

`Investor flows` 블록 바로 뒤(있을 때만 렌더되는 조건 블록 밖)에 삽입:

```astro
  {flowChart && (
    <>
      <h2>Cumulative investor flows (30 sessions)</h2>
      <figure set:html={flowChart} />
      <p class="asof">Cumulative net buying in shares since the start of the window.</p>
    </>
  )}
```

- [ ] **Step 2: 섹터 테이블에 로테이션 산점도 추가** — `SectorTable.astro` frontmatter 끝에 삽입:

```js
const charts = import.meta.glob("../data/charts/*.svg", {
  query: "?raw", import: "default", eager: true,
});
const scatter = charts[`../data/charts/${sector}-scatter.svg`];
```

`<div class="table-scroll">` 앞에 삽입:

```astro
{scatter && <figure set:html={scatter} />}
```

- [ ] **Step 3: figure 여백 스타일 추가** — `Base.astro`의 전역 `<style is:global>` 안에 추가:

```css
  figure { margin: 0.8rem 0; }
```

- [ ] **Step 4: `run_daily.sh`에 charts 단계 추가** — `verify_ledger` 줄 다음에 삽입:

```bash
  "$PY" -m pipeline.charts || echo "CHARTS FAILED (continuing)"
```

- [ ] **Step 5: 빌드 실증**

Run: `cd site && npm run build`
Expected: 오류 없이 페이지 생성. 이후 `grep -c "<svg" dist/stocks/005930/index.html` 이 1 이상, `grep -c "<svg" dist/semiconductor/index.html` 이 1 이상.

- [ ] **Step 6: 커밋·배포·라이브 확인**

```bash
git add site pipeline/run_daily.sh && git commit -m "feat: 종목·섹터 페이지에 인라인 SVG 차트 삽입" && git push origin main
```
배포 후 `curl -s https://chipandcell.com/stocks/005930/ | grep -c "<svg"` 가 1 이상인지 확인한다.

---

## Phase 3 — 밸류체인

### Task 8: 밸류체인 SSOT (`valuechain.py`)

**Files:**
- Create: `pipeline/valuechain.py`, `pipeline/tests/test_valuechain.py`

**Interfaces:**
- Consumes: `pipeline.tickers.TICKERS`
- Produces:
  - `STAGES: dict[str, list[dict]]` — `{sector: [{"key","label","codes":[...]}, ...]}`, 상위 단계부터 순서대로
  - `LINKS: list[dict]` — `{"from","to","label","source","year"}`. 근거 확인된 것만.
  - `stage_of(code) -> str | None`

- [ ] **Step 1: 실패하는 테스트 작성** (`pipeline/tests/test_valuechain.py`)

```python
from pipeline.tickers import TICKERS
from pipeline.valuechain import STAGES, LINKS, stage_of


def test_every_ticker_has_exactly_one_stage():
    for code, en, _kr, sector in TICKERS:
        stages = [s["key"] for s in STAGES[sector] if code in s["codes"]]
        assert len(stages) == 1, f"{code} {en}: {stages}"


def test_stages_only_reference_known_codes():
    known = {t[0] for t in TICKERS}
    for sector, stages in STAGES.items():
        for s in stages:
            assert set(s["codes"]) <= known


def test_links_are_sourced_and_reference_known_codes():
    known = {t[0] for t in TICKERS}
    for l in LINKS:
        assert l["from"] in known and l["to"] in known
        assert l["source"].startswith("http") and isinstance(l["year"], int)


def test_stage_of():
    assert stage_of("005930") is not None
    assert stage_of("999999") is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest pipeline/tests/test_valuechain.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.valuechain'`

- [ ] **Step 3: 단계 배정 근거 확인** — 27종목 각각의 사업 영역을 공개 자료로 확인한 뒤 단계를 배정한다. 확인 방법: `fdr.StockListing("KRX")`의 업종 필드와 각 사 공식 소개(회사 홈페이지·DART 사업의 개요). 추정으로 배정하지 않는다.

- [ ] **Step 4: 구현** (`pipeline/valuechain.py`) — 아래 골격에 Step 3에서 확인한 배정을 채운다. 27종목 전부가 정확히 한 단계에 속해야 하며(테스트가 강제), `LINKS`는 출처 URL과 연도를 확인한 관계만 넣는다. 하나도 확인하지 못하면 `LINKS = []`로 두고 계층도만 그린다.

```python
"""밸류체인 단계 SSOT. 관계선은 공개 자료로 확인된 것만 포함한다.

각 종목은 정확히 한 단계에 속한다(test_valuechain이 강제).
LINKS의 source는 확인 가능한 URL, year는 그 자료의 연도여야 한다.
"""
STAGES = {
    "semiconductor": [
        {"key": "memory", "label": "Memory & Foundry", "codes": []},
        {"key": "equipment", "label": "Equipment", "codes": []},
        {"key": "materials", "label": "Materials", "codes": []},
        {"key": "backend", "label": "Back-end & Test", "codes": []},
    ],
    "battery": [
        {"key": "cell", "label": "Cell Makers", "codes": []},
        {"key": "cathode", "label": "Cathode & Precursor", "codes": []},
        {"key": "submaterials", "label": "Sub-materials & Equipment", "codes": []},
    ],
}

LINKS = []


def stage_of(code):
    for stages in STAGES.values():
        for s in stages:
            if code in s["codes"]:
                return s["key"]
    return None
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest pipeline/tests -q`
Expected: PASS — 특히 `test_every_ticker_has_exactly_one_stage`가 27종목 전부를 검사한다.

- [ ] **Step 6: 커밋**

```bash
git add pipeline/valuechain.py pipeline/tests/test_valuechain.py
git commit -m "feat: 밸류체인 단계 SSOT(전 종목 배정 검증)"
```

---

### Task 9: 밸류체인 계층도 렌더

**Files:**
- Create: `site/src/data/valuechain.json`, `site/src/components/ValueChain.astro`
- Modify: `pipeline/valuechain.py` (export 함수), `pipeline/charts.py` 호출부 또는 `run_daily.sh`
- Modify: `site/src/pages/semiconductor.astro`, `site/src/pages/battery.astro`

**Interfaces:**
- Produces: `valuechain.export_json()` → `site/src/data/valuechain.json` = `{"stages": STAGES, "links": LINKS}`
- `ValueChain.astro` props: `sector: string`

- [ ] **Step 1: export 함수 추가** — `pipeline/valuechain.py` 하단에 추가:

```python
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_DIR, "..", "site", "src", "data", "valuechain.json")


def export_json():
    with open(OUT, "w") as f:
        json.dump({"stages": STAGES, "links": LINKS}, f, ensure_ascii=False, indent=1)
    print(f"valuechain OK stages={sum(len(v) for v in STAGES.values())} links={len(LINKS)}")


if __name__ == "__main__":
    export_json()
```

- [ ] **Step 2: 실행해 JSON 생성 확인**

Run: `.venv/bin/python -m pipeline.valuechain && cat site/src/data/valuechain.json | head -5`
Expected: `valuechain OK stages=7 links=N`

- [ ] **Step 3: `ValueChain.astro` 작성** — 단계를 위에서 아래로 쌓고 각 노드에 라이브 수치를 붙인다. HTML/CSS 그리드로 그리며 SVG는 쓰지 않는다(반응형이 쉽고 텍스트가 그대로 크롤링된다).

```astro
---
import stocksData from "../data/stocks.json";
import vc from "../data/valuechain.json";
import { pct } from "../lib/fmt.js";

const { sector } = Astro.props;
const stages = vc.stages[sector] ?? [];
const links = (vc.links ?? []).filter(
  (l) => stocksData.stocks[l.from]?.sector === sector
);
---
<div class="vc">
  {stages.map((stage) => (
    <div class="vc-stage">
      <h3>{stage.label}</h3>
      <div class="vc-nodes">
        {stage.codes.map((code) => {
          const s = stocksData.stocks[code];
          if (!s) return null;
          const d = pct(s.pct);
          const r = pct(s.r20);
          return (
            <a class="vc-node" href={`/stocks/${code}/`}>
              <span class="vc-name">{s.name_en}</span>
              <span class="vc-nums">
                <span class={d.cls}>{d.text}</span>
                <span class="code">20d </span><span class={r.cls}>{r.text}</span>
              </span>
            </a>
          );
        })}
      </div>
    </div>
  ))}
</div>
{links.length > 0 && (
  <details class="vc-links">
    <summary>Documented supply relationships ({links.length})</summary>
    <ul>
      {links.map((l) => (
        <li>
          {stocksData.stocks[l.from]?.name_en} → {stocksData.stocks[l.to]?.name_en}: {l.label}
          {" "}(<a href={l.source} rel="nofollow noopener" target="_blank">source, {l.year}</a>)
        </li>
      ))}
    </ul>
  </details>
)}
<style>
  .vc { display: flex; flex-direction: column; gap: 0.5rem; margin: 1rem 0; }
  .vc-stage { border: 1px solid var(--line); border-radius: 8px; padding: 0.6rem 0.8rem;
    background: var(--card); }
  .vc-stage h3 { margin: 0 0 0.5rem; font-size: 0.85rem; letter-spacing: 0.04em;
    text-transform: uppercase; color: var(--muted); }
  .vc-nodes { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    gap: 0.4rem; }
  .vc-node { display: flex; justify-content: space-between; gap: 0.5rem;
    border: 1px solid var(--line); border-radius: 6px; padding: 0.35rem 0.5rem;
    font-size: 0.85rem; color: var(--fg); }
  .vc-node:hover { border-color: var(--accent); text-decoration: none; }
  .vc-nums { white-space: nowrap; font-variant-numeric: tabular-nums; }
  .vc-links { margin: 0.5rem 0 1rem; font-size: 0.9rem; }
</style>
```

- [ ] **Step 4: 섹터 페이지에 삽입** — `semiconductor.astro`와 `battery.astro` 각각에서 `import SectorTable ...` 다음 줄에 `import ValueChain from "../components/ValueChain.astro";`를 추가하고, `<SectorTable ... />` 앞에 삽입:

```astro
  <h2>Value chain</h2>
  <ValueChain sector="semiconductor" />
```
(battery.astro는 `sector="battery"`)

- [ ] **Step 5: `run_daily.sh`에 export 추가** — `charts` 줄 앞에 삽입:

```bash
  "$PY" -m pipeline.valuechain || echo "VALUECHAIN FAILED (continuing)"
```

- [ ] **Step 6: 빌드·배포·라이브 확인**

Run: `cd site && npm run build && grep -c "vc-node" dist/semiconductor/index.html`
Expected: 15 (반도체 커버리지 수)

```bash
git add site pipeline && git commit -m "feat: 밸류체인 계층도(섹터 페이지)" && git push origin main
```
배포 후 `curl -s https://chipandcell.com/semiconductor/ | grep -c "vc-node"` 확인.

---

## Phase 4 — 사후검증 노출

### Task 10: Track record 섹션

**Files:**
- Create: `site/src/components/TrackRecord.astro`
- Modify: `site/src/pages/stocks/[code].astro`

**Interfaces:**
- Consumes: `site/src/data/history/ledger.json`
- Props: `code: string`

- [ ] **Step 1: `TrackRecord.astro` 작성** — 최근 12건을 최신순으로 보여주고, 검증된 항목은 결과를 함께 표시한다. 백필 레코드는 표시로 구분한다.

```astro
---
import ledger from "../data/history/ledger.json";
import { won, pct } from "../lib/fmt.js";

const { code } = Astro.props;
const rows = ledger.records
  .filter((r) => r.code === code)
  .sort((a, b) => (a.date < b.date ? 1 : -1))
  .slice(0, 12);
const verifiedCount = ledger.records.filter((r) => r.code === code && r.verified).length;
---
{rows.length > 0 && (
  <>
    <h2>Track record</h2>
    <p class="asof">
      What the data showed on each date, and where the stock actually stood 20 trading
      sessions later. Outcomes are published as recorded — favourable or not.
      {verifiedCount > 0 && <> {verifiedCount} of these observations have completed their window.</>}
    </p>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Date</th><th>Close</th><th>52w pos</th><th>Foreign 5d</th><th>After 20 sessions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const v = r.verified;
            const vp = v ? pct(v.return_pct) : null;
            return (
              <tr>
                <td>
                  {r.date}
                  {r.backfilled && <span class="code" title="Computed retrospectively"> ·retro</span>}
                </td>
                <td>{won(r.close)}</td>
                <td>{r.pos52}%</td>
                <td>{r.flow5_f == null ? "—" : r.flow5_f.toLocaleString("en-US")}</td>
                <td>{vp ? <span class={vp.cls}>{vp.text}</span> : <span class="code">pending</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    {rows.some((r) => r.note) && (
      <ul class="notes">
        {rows.filter((r) => r.note).map((r) => (
          <li>
            <span class="asof">{r.date}</span> {r.note}
            {r.note_post && <> (<a href={`/posts/${r.note_post}/`}>full note</a>)</>}
          </li>
        ))}
      </ul>
    )}
    <p class="asof">
      Rows marked <strong>·retro</strong> were computed retrospectively from historical data
      when this section was introduced — they are facts about those dates, not observations
      published at the time. See <a href="/methodology/">methodology</a>.
    </p>
  </>
)}
<style>
  .notes { font-size: 0.9rem; padding-left: 1.1rem; }
  .notes li { margin-bottom: 0.4rem; }
</style>
```

- [ ] **Step 2: 종목 페이지에 삽입** — `[code].astro` frontmatter에 `import TrackRecord from "../../components/TrackRecord.astro";`를 추가하고, `<h2>Sector standing</h2>` 블록 뒤에 삽입:

```astro
  <TrackRecord code={code} />
```

- [ ] **Step 3: methodology 페이지에 설명 추가** — `methodology.astro`의 `<h2>Disclaimer</h2>` 앞에 삽입:

```astro
  <h2>Track record and verification</h2>
  <p>
    Each trading day we record a structured snapshot of every covered stock: closing price,
    position in its 52-week range, distance from its moving averages, and five-session
    cumulative foreign and institutional net buying. Twenty trading sessions later we attach
    what actually happened to the price. These are observations, not forecasts, and results
    are published whether or not they flatter us.
  </p>
  <p>
    Snapshots marked <strong>·retro</strong> were computed retrospectively from historical
    data when the feature launched. They are accurate as facts about those dates, but they
    were not published at the time — only later snapshots carry a timestamped record.
  </p>
```

- [ ] **Step 4: 빌드 실증**

Run: `cd site && npm run build && grep -c "Track record" dist/stocks/005930/index.html`
Expected: 1

- [ ] **Step 5: 커밋·배포·라이브 확인**

```bash
git add site && git commit -m "feat: 종목별 Track record 섹션(D+20 검증 결과 표시)" && git push origin main
```
배포 후 `curl -s https://chipandcell.com/stocks/005930/ | grep -c "Track record"` 가 1인지 확인한다.

- [ ] **Step 6: 전체 배치 최종 실증** — 미니에서 확장된 일일 배치를 kickstart 해 `flow_history → record_ledger → verify_ledger → valuechain → charts → 글 생성 → push`가 완주하는지 확인하고, 라이브 사이트에서 차트·밸류체인·Track record가 모두 보이는지 확인한다.

---

## Self-Review 결과

**스펙 커버리지:** 정직성 규칙(Task 3 `backfilled`·Task 4 무조건 기록·Task 10 retro 표기와 methodology 설명·Task 8 출처 강제 테스트) ✓ / 데이터 계층 flows·ledger 스키마(Task 2·3) ✓ / as-of 계산(Task 1) ✓ / 차트 3종과 CSS 변수 주의사항(Task 6) ✓ / `?raw` glob 삽입(Task 7) ✓ / 밸류체인 계층도+검증된 관계선(Task 8·9) ✓ / Track record(Task 10) ✓ / 파이프라인 순서와 비차단 실패(Task 5·7·9) ✓ / 테스트 항목 전부 과제에 배치 ✓ / 비목표(로고·예측·별도 DB·JS 차트·신규 URL) 위반 없음 ✓

**플레이스홀더 점검:** Task 8 Step 3~4의 단계 배정은 "공개 자료로 확인 후 채운다"는 실행 지시이며, 테스트가 27종목 전건 배정을 강제하므로 미완성 상태로 통과할 수 없다. 그 외 TBD·"적절히 처리" 류 없음.

**타입 일관성:** `flow5(store, code, date) -> (int|None, int|None)`가 Task 2 정의와 Task 3 사용에서 일치 ✓ / `snapshot(code, m, store, date, backfilled)` 인자 순서가 Task 3 정의·테스트·`run()` 호출에서 일치 ✓ / `pick_forward(closes, date, horizon)` 반환 `(date, close)`가 Task 4 `run()` 사용과 일치 ✓ / 레코드 키(`flow5_f`, `vs_ma20`, `verified.return_pct`)가 Task 3 생성·Task 4 기입·Task 10 렌더에서 동일 ✓ / `STAGES`/`LINKS` 구조가 Task 8 정의·Task 9 export·`ValueChain.astro` 소비에서 일치 ✓ / 차트 파일명 규칙 `{code}-candle.svg`·`{code}-flow.svg`·`{sector}-scatter.svg`가 Task 6 생성·Task 7 조회에서 일치 ✓
