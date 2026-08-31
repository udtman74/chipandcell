from pipeline.verify_ledger import pick_forward

CLOSES = [(f"2026-08-{d:02d}", 100.0 + d) for d in range(1, 21)]  # 8/01~8/20


def test_pick_forward_selects_nth_trading_day_after():
    assert pick_forward(CLOSES, "2026-08-05", horizon=3) == ("2026-08-08", 108.0)


def test_pick_forward_none_when_horizon_not_reached():
    assert pick_forward(CLOSES, "2026-08-19", horizon=3) is None


def test_pick_forward_ignores_same_day():
    assert pick_forward(CLOSES, "2026-08-01", horizon=1) == ("2026-08-02", 102.0)
