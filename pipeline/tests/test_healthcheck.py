"""healthcheck 테스트 — 2026-11-13 사고의 두 증상을 탐지하는지 확인한다."""
import json

import pytest

from pipeline import healthcheck
from pipeline import status as runstatus
from pipeline.tests.conftest import ASOF, read, trading_days, write_fixture, write_json


@pytest.fixture(autouse=True)
def _status(tmp_path, monkeypatch):
    monkeypatch.setattr(runstatus, "STATE", str(tmp_path / "status.json"))


def ids(rep):
    return {c["id"]: c for c in rep["checks"]}


def fixture_ok(tmp_path, **kw):
    """모든 검사를 통과하는 기본 상태(글·주간·수급 모두 정상)."""
    kw.setdefault("weekly_dates", ["2026-11-13", "2026-11-06"])
    data_dir, posts_dir, doc = write_fixture(tmp_path, **kw)
    return data_dir, posts_dir, doc


def test_healthy_fixture_passes(tmp_path):
    data_dir, posts_dir, _doc = fixture_ok(tmp_path)
    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir))
    assert rep["ok"], rep["failed"]
    assert ids(rep)["flow.coverage"]["status"] == "pass"
    assert ids(rep)["posts.deep_dive"]["status"] == "pass"


def test_zero_daily_change_contradicting_ledger_fails(tmp_path):
    """천보(278280) 사고: 장부상 +0.33%인데 화면이 0.00%인 상태를 잡는다."""
    data_dir, posts_dir, doc = fixture_ok(tmp_path)
    payload = read(data_dir / "stocks.json")
    s = payload["stocks"]["278280"]
    s["close"] = s["close"] + 1          # 전일 종가와 같아진 척(0.00%)
    s["pct"] = 0.0
    write_json(str(data_dir / "stocks.json"), payload)

    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir))
    assert not rep["ok"]
    assert "metrics.zero_return" in rep["failed"]
    assert any("278280" in c["detail"] for c in rep["checks"] if c["id"] == "metrics.zero_return")


def test_zero_return_metric_contradicting_ledger_fails(tmp_path):
    """가온칩스(399720) 사고: 20일 수익률이 0.00%인데 기준일 종가는 다른 상태를 잡는다."""
    data_dir, posts_dir, _doc = fixture_ok(tmp_path)
    payload = read(data_dir / "stocks.json")
    payload["stocks"]["399720"]["r20"] = 0.0
    write_json(str(data_dir / "stocks.json"), payload)

    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir))
    assert "metrics.zero_return" in rep["failed"]
    assert any("399720" in c["detail"] for c in rep["checks"] if c["id"] == "metrics.zero_return")


def test_tampered_metric_fails_self_consistency(tmp_path):
    data_dir, posts_dir, _doc = fixture_ok(tmp_path)
    payload = read(data_dir / "stocks.json")
    payload["stocks"]["005930"]["r20"] = 12.34          # bases와 모순
    write_json(str(data_dir / "stocks.json"), payload)
    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir))
    assert "metrics.self_consistent" in rep["failed"]


def test_flow_missing_while_flows_json_has_rows_fails(tmp_path):
    """2026-11-13 사고: flows.json에는 있는데 사이트 flow가 전부 null이면 FAIL."""
    data_dir, posts_dir, doc = fixture_ok(tmp_path, flow=False)
    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir))
    assert "flow.coverage" in rep["failed"]
    detail = ids(rep)["flow.coverage"]["detail"]
    assert "flows.json에는" in detail


def test_flow_missing_without_upstream_data_is_only_a_warning(tmp_path):
    """상류(KIS)까지 비어 있는 경우는 WARN — 발행 측 결함과 구분한다."""
    data_dir, posts_dir, _doc = fixture_ok(tmp_path, flow=False)
    write_json(str(data_dir / "history" / "flows.json"), {"updated": "", "flows": {}})
    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir))
    assert ids(rep)["flow.coverage"]["status"] == "warn"
    assert rep["ok"]


def test_missing_deep_dive_for_recent_trading_day_fails(tmp_path):
    """11-06·11-13 주간 리뷰 누락과 평일 6일 심층 글 누락을 잡는다."""
    days = trading_days(25)
    data_dir, posts_dir, _doc = write_fixture(
        tmp_path, posts_days=[days[-1], days[-2]], weekly_dates=[days[-1]])
    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir))
    assert "posts.deep_dive" in rep["failed"]
    assert ids(rep)["posts.deep_dive"]["status"] == "fail"


def test_missing_weekly_review_fails(tmp_path):
    data_dir, posts_dir, _doc = write_fixture(tmp_path, weekly_dates=["2026-11-06"])
    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir))
    assert "posts.weekly" in rep["failed"]
    assert "2026-11-13" in ids(rep)["posts.weekly"]["detail"]


def test_expect_today_requires_todays_post(tmp_path):
    data_dir, posts_dir, _doc = fixture_ok(tmp_path)
    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir),
                            expect_today="2026-11-13")
    assert ids(rep)["posts.today"]["status"] == "pass"

    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(posts_dir),
                            expect_today="2026-11-15")      # 글 없는 날
    assert "posts.today" in rep["failed"]


def test_missing_stocks_file_fails_cleanly(tmp_path):
    data_dir = tmp_path / "empty"
    data_dir.mkdir()
    rep = healthcheck.check(data_dir=str(data_dir), posts_dir=str(tmp_path))
    assert rep["ok"] is False and rep["failed"] == ["stocks.json"]


def test_main_exit_codes_and_status(tmp_path, monkeypatch, capsys):
    data_dir, posts_dir, _doc = fixture_ok(tmp_path)
    monkeypatch.setattr(healthcheck, "DATA", str(data_dir))
    monkeypatch.setattr(healthcheck, "POSTS", str(posts_dir))
    assert healthcheck.main([]) == 0
    assert "OK" in capsys.readouterr().out

    payload = read(data_dir / "stocks.json")
    payload["stocks"]["005930"]["r20"] = 99.9
    write_json(str(data_dir / "stocks.json"), payload)
    assert healthcheck.main(["--quiet"]) == 1
    status = json.load(open(tmp_path / "status.json"))
    assert status["steps"]["healthcheck"]["status"] == "failed"
