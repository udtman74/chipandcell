import numpy as np
import pandas as pd

from pipeline.metrics import compute


def _df(closes):
    idx = pd.bdate_range("2025-01-01", periods=len(closes))
    return pd.DataFrame({"Close": closes, "Volume": [1000] * len(closes)}, index=idx)


def test_compute_basic():
    m = compute(_df(list(range(100, 400))))  # 단조 상승 300일
    assert m["close"] == 399 and m["pos52"] == 100.0
    assert m["ma20"] == np.mean(range(380, 400))
    assert round(m["r5"], 2) == round((399 / 394 - 1) * 100, 2)


def test_compute_flat_series_pos52_degenerate():
    m = compute(_df([100.0] * 300))
    assert m["pos52"] == 50.0 and m["pct"] == 0.0


def test_compute_asof_slices_series():
    df = _df(list(range(100, 400)))          # 2025-01-01부터 300 영업일, 단조 상승
    asof = df.index[199].strftime("%Y-%m-%d")
    m = compute(df, asof=asof)
    assert m["close"] == 299                  # 200번째 봉 종가
    assert m["date"] == asof


def test_compute_asof_none_uses_full_series():
    df = _df(list(range(100, 400)))
    assert compute(df)["close"] == 399
