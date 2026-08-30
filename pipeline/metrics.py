"""OHLCV DataFrame(fdr 형식) → 지표 dict. 52주=252거래일 근사."""


def compute(df):
    df = df.dropna(subset=["Close"]).tail(300)
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
