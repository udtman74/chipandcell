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
