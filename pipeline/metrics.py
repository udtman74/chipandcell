"""OHLCV DataFrame(fdr 형식) → 지표 dict. 52주=252거래일 근사.

계산 규칙 (2026-11-15 강화 — 홈 수치 0.00% 사고 이후):

1. **정규화**: 날짜 인덱스로 정렬하고, 같은 날짜의 행이 여러 개면 마지막 행만 남긴다.
   fdr 응답에는 같은 세션의 행이 두 번 들어오는 경우가 있다(장중 스냅샷 행 뒤에 확정
   일봉 행이 붙는 형태). 정규화 없이 그대로 쓰면 종가가 같은 두 행이 이웃이 되어
   당일 등락률이 **0.00%로 둔갑**하고, 5/20/60일 전 종가의 위치도 하루씩 밀린다.
   2026-11-13 스냅샷의 천보(278280) 당일 0.00%(장부상 +0.33%)가 이 경로로 만들어진다.

2. **날짜 기준 비교**: 모든 비교는 "행 위치"가 아니라 "서로 다른 날짜"로 한다.
   중복 행·결측 세션이 섞여 있어도 같은 봉을 두 번 비교하는 일이 없다.

3. **기준일 공개**: 각 수익률의 기준일과 기준 종가를 `bases`로 함께 돌려준다.
   화면 숫자·장부·사후검증이 같은 근거를 참조하게 하기 위함이다(정직성 규칙).
   가온칩스(399720) r20 0.00%는 기준일 종가가 당일 종가와 같아진 경우이며, `bases`를
   보면 어떤 날짜·종가를 썼는지 즉시 드러난다.
"""
import pandas as pd

RETURN_WINDOWS = (5, 20, 60)
MAX_ROWS = 400          # 52주(252) + 60일 지표 + 중복·결측 여유


def normalize(df):
    """가격 프레임 정규화: 종가 결측 제거 → 중복 날짜 병합(마지막 값) → 날짜 정렬."""
    if df is None or len(df) == 0:
        raise ValueError("empty price frame")
    if "Close" not in df.columns:
        raise ValueError("price frame has no Close column")
    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index)
    out = out.dropna(subset=["Close"])
    if len(out) == 0:
        raise ValueError("price frame has no usable Close row")
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


def compute(df, asof=None):
    """asof("YYYY-MM-DD") 지정 시 그 일자까지만 사용해 과거 시점 지표를 재현한다.

    과거 레코드에 오늘 기준 값을 넣으면 미래 정보 누출이자 사실 오류이므로,
    백필 스냅샷은 반드시 asof를 지정해 계산한다.
    """
    df = normalize(df)
    if asof is not None:
        df = df[df.index <= pd.Timestamp(asof)]
        if len(df) == 0:
            raise ValueError(f"no price rows on or before {asof}")
    df = df.tail(MAX_ROWS)
    c = df["Close"].astype(float)
    if len(c) < 2:
        # 1봉뿐이면 등락률을 만들 수 없다. 예전에는 iloc[-2]에서 IndexError로 터져
        # 종목이 export에서 통째로 빠졌다.
        raise ValueError(f"need >=2 sessions for a daily change (got {len(c)})")

    close = float(c.iloc[-1])
    prev = float(c.iloc[-2])
    y = c.tail(252)
    hi52, lo52 = float(y.max()), float(y.min())

    def _base(n):
        """n거래일 전 봉. 서로 다른 날짜이며, 없으면 (None, None)."""
        if len(c) <= n:
            return None, None
        return c.index[-1 - n], float(c.iloc[-1 - n])

    bases = {"pct": {"date": c.index[-2].strftime("%Y-%m-%d"), "close": prev}}
    rets = {}
    for n in RETURN_WINDOWS:
        d, p = _base(n)
        key = f"r{n}"
        rets[key] = None if (d is None or p == 0) else float((close / p - 1) * 100)
        bases[key] = None if d is None else {"date": d.strftime("%Y-%m-%d"), "close": p}

    return {
        "close": close,
        "pct": round((close / prev - 1) * 100, 2),
        "value_bil": round(close * float(df["Volume"].iloc[-1]) / 1e9, 1),
        "hi52": hi52,
        "lo52": lo52,
        "pos52": round((close - lo52) / (hi52 - lo52) * 100, 1) if hi52 > lo52 else 50.0,
        "ma20": float(c.tail(20).mean()),
        "ma60": float(c.tail(60).mean()),
        **rets,
        "date": c.index[-1].strftime("%Y-%m-%d"),
        "prev_date": bases["pct"]["date"],
        "bases": bases,
    }


def implied_base(close, value):
    """종가와 수익률(%)로 그 수익률이 쓴 기준 종가를 역산한다(불일치 추적용)."""
    if value is None or value == -100:
        return None
    return round(close / (1 + value / 100), 4)


def inconsistencies(m, tol=0.05):
    """지표 dict가 스스로 모순되지 않는지 검사한다(기준일 종가로 재계산).

    반환: [(필드, 기대값, 실제값, 허용오차)] — 비어 있으면 일관됨.
    """
    problems = []
    bases = m.get("bases") or {}
    for field in ("pct", "r5", "r20", "r60"):
        b = bases.get(field)
        if not b or not b.get("close"):
            continue
        expect = round((m["close"] / b["close"] - 1) * 100, 2)
        actual = round(m.get(field), 2) if m.get(field) is not None else None
        if actual is None or abs(expect - actual) > tol:
            problems.append((field, expect, actual, tol))
    if m.get("prev_date") and m.get("date") and m["prev_date"] >= m["date"]:
        problems.append(("prev_date", "<" + m["date"], m["prev_date"], 0))
    return problems
