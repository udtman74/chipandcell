from pipeline.gen_deep_dive import pick_target


def test_event_priority():
    stocks = {"A": {"pct": 1.0}, "B": {"pct": -7.2}, "C": {"pct": 3.0}}
    st = {"queue": ["A", "B", "C"], "last_events": {}}
    assert pick_target(stocks, st, today="2026-08-30") == "B"  # |pct|>=5 이벤트 우선


def test_event_cooldown():
    stocks = {"A": {"pct": 6.0}, "B": {"pct": 1.0}}
    st = {"queue": ["B", "A"], "last_events": {"A": "2026-08-28"}}  # 7일 내 재이벤트
    assert pick_target(stocks, st, today="2026-08-30") == "B"  # 쿨다운 → 로테이션


def test_rotation_when_quiet():
    stocks = {"A": {"pct": 1.0}, "B": {"pct": -2.0}}
    st = {"queue": ["B", "A"], "last_events": {}}
    assert pick_target(stocks, st, today="2026-08-30") == "B"
    assert st["queue"] == ["A", "B"]  # 큐 회전
