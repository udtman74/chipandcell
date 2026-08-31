"""OHLCV DataFrame(fdr 형식) → 지표 dict. 52주=252거래일 근사."""
import pandas as pd


def compute(df, asof=None):
    """asof("YYYY-MM-DD") 지정 시 그 일자까지만 사용해 과거 시점 지표를 재현한다.

    과거 레코드에 오늘 기준 값을 넣으면 미래 정보 누출이자 사실 오류이므로,
    백필 스냅샷은 반드시 asof를 지정해 계산한다.
    """
    df = df.dropna(subset=["Close"])
    if asof is not None:
        df = df[df.index <= pd.Timestamp(asof)]
    df = df.tail(300)
    c = df["Close"]
    close = float(c.iloc[-1])
    prev = float(c.iloc[-2])
    y = c.tail(252)
    hi52, lo52 = float(y.max()), float(y.min())

    def _r(n):
        return float((close / c.iloc[-1 - n] - 1) * 100) if len(c) > n else None

    return {
        "close": close,
        "pct": round((close / prev - 1) * 100, 2),
        "value_bil": round(close * float(df["Volume"].iloc[-1]) / 1e9, 1),
        "hi52": hi52,
        "lo52": lo52,
        "pos52": round((close - lo52) / (hi52 - lo52) * 100, 1) if hi52 > lo52 else 50.0,
        "ma20": float(c.tail(20).mean()),
        "ma60": float(c.tail(60).mean()),
        "r5": _r(5),
        "r20": _r(20),
        "r60": _r(60),
        "date": df.index[-1].strftime("%Y-%m-%d"),
    }
