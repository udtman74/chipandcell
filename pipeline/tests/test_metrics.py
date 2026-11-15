import pandas as pd
import pytest

from pipeline.metrics import compute, implied_base, inconsistencies, normalize

from pipeline.tests.conftest import frame

import numpy as np


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


# --- 2026-11-13 사고 재발 방지 ---------------------------------------------
# 증상: 천보(278280) 당일 등락 0.00%(장부상 +0.33%), 가온칩스(399720) 20일 수익률
#       0.00%(장부상 +1.18%). 두 값 모두 "같은 종가를 두 번 비교"하면 만들어지는 숫자다.

def test_duplicate_final_session_does_not_zero_daily_change():
    """같은 세션 행이 두 번 들어와도 당일 등락률이 0.00%가 되면 안 된다(천보 회귀)."""
    clean = _df([100, 101, 102, 103, 104, 110])
    dirty = pd.concat([clean, clean.iloc[[-1]]])      # 마지막 행 중복(장중 행 + 확정 행)

    a, b = compute(clean), compute(dirty)
    assert b["pct"] == a["pct"] == round((110 / 104 - 1) * 100, 2)
    assert b["pct"] != 0.0
    assert b["prev_date"] == a["prev_date"] == clean.index[-2].strftime("%Y-%m-%d")
    assert b["prev_date"] < b["date"]


def test_duplicate_final_session_does_not_shift_returns():
    """중복 행은 5/20/60일 기준 위치도 밀어서는 안 된다."""
    closes = [100 + k for k in range(80)] + [200]
    clean = _df(closes)
    dirty = pd.concat([clean, clean.iloc[[-1]]])
    a, b = compute(clean), compute(dirty)
    for field in ("r5", "r20", "r60"):
        assert a[field] == pytest.approx(b[field], rel=1e-12), field
        assert a["bases"][field]["date"] == b["bases"][field]["date"], field


def test_duplicate_middle_session_is_merged():
    """중간 날짜가 중복돼도 뒤 시세가 기준 위치를 밀지 않는다."""
    clean = _df([100 + k for k in range(40)])
    dup = clean.iloc[[10]]
    dirty = pd.concat([clean.iloc[:11], dup, clean.iloc[11:]])
    a, b = compute(clean), compute(dirty)
    assert b["close"] == a["close"]
    assert b["r20"] == pytest.approx(a["r20"], rel=1e-12)
    assert b["bases"]["r20"]["date"] == a["bases"]["r20"]["date"]


def test_out_of_order_rows_are_sorted():
    clean = _df([100 + k for k in range(40)])
    shuffled = clean.iloc[list(range(1, 40)) + [0]]        # 첫 행을 끝으로
    m = compute(shuffled)
    assert m["close"] == clean["Close"].iloc[-1]
    assert m["date"] == clean.index[-1].strftime("%Y-%m-%d")


def test_zero_return_always_has_distinct_sessions():
    """0.00%는 서로 다른 두 세션의 종가가 같을 때만 나온다(중복 행 때문이면 안 된다)."""
    m = compute(_df([100, 120, 120]))
    assert m["pct"] == 0.0
    assert m["prev_date"] == "2025-01-02" and m["date"] == "2025-01-03"


def test_bases_record_the_date_and_close_used():
    """기준일·기준 종가를 남겨 0.00%든 무엇이든 근거를 추적할 수 있게 한다."""
    df = _df([100 + k for k in range(30)])
    m = compute(df)
    base = m["bases"]["r20"]
    assert base["date"] == df.index[-21].strftime("%Y-%m-%d")
    assert base["close"] == df["Close"].iloc[-21]
    assert m["bases"]["pct"]["close"] == df["Close"].iloc[-2]
    assert m["prev_date"] == base["date"] or m["prev_date"] == df.index[-2].strftime("%Y-%m-%d")
    assert implied_base(m["close"], m["r20"]) == pytest.approx(base["close"], rel=1e-9)


def test_bases_are_none_when_history_is_too_short():
    m = compute(_df([100, 101, 102]))
    assert m["r5"] is None and m["bases"]["r5"] is None
    assert m["r20"] is None and m["bases"]["r20"] is None


def test_single_row_raises_clear_error():
    with pytest.raises(ValueError, match="2 sessions"):
        compute(_df([100]))


def test_nan_close_rows_are_dropped():
    df = _df([100, 101, 102, 103])
    df.loc[df.index[-1], "Close"] = float("nan")
    m = compute(df)
    assert m["close"] == 102 and m["date"] == df.index[-2].strftime("%Y-%m-%d")


def test_normalize_is_idempotent():
    df = _df([100, 101, 102])
    once = normalize(df)
    twice = normalize(once)
    assert once.equals(twice)


def test_inconsistencies_flags_tampered_value():
    m = compute(_df([100 + k for k in range(40)]))
    assert inconsistencies(m) == []
    m["r20"] = 0.0                                  # 화면에 0.00%로 둔갑한 상태
    problems = inconsistencies(m)
    assert [p[0] for p in problems] == ["r20"]


def test_inconsistencies_flags_prev_date_not_before_date():
    m = compute(_df([100 + k for k in range(40)]))
    m["prev_date"] = m["date"]
    assert "prev_date" in [p[0] for p in inconsistencies(m)]
