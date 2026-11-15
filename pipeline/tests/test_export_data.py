"""export_data 회귀 테스트 — 수급 전면 누락(2026-11-13) 재발 방지.

증상: stocks.json(asof 11-13)의 27종목 flow가 모두 null인데 flows.json에는 11-13 행이
있었다. export_data._flow()가 종목마다 get_access_token()을 새로 불러 27회 토큰 발급을
시도했고(KIS는 1분 1회 제한), `except Exception: return None`이 사유를 삼켰다.
"""
import json

import pytest

from pipeline import export_data
from pipeline import status as runstatus
from pipeline.tickers import TICKERS
from pipeline.tests.conftest import ASOF, price_frames, write_json


class FakeReader:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def __call__(self, symbol):
        self.calls.append(symbol)
        return self.frames[symbol]


class FakeKis:
    """kis_api 대역. 토큰 발급 횟수·수급 호출 횟수를 센다."""

    def __init__(self, fail=(), fail_times=0):
        self.tokens = 0
        self.calls = 0
        self._fail = set(fail)
        self._fail_times = fail_times
        self._left = {}

    def get_access_token(self):
        self.tokens += 1
        return "TOKEN"

    def get_investor_trend(self, code, token):
        self.calls += 1
        if code in self._fail:
            raise RuntimeError("EGW00133: 접근토큰 발급 간격이 1분 이하입니다")
        if self._fail_times:
            left = self._left.get(code, self._fail_times)
            if left:
                self._left[code] = left - 1
                raise RuntimeError("429 rate limit")
        return {"foreign_net": 1, "inst_net": -2, "individual_net": 3}


class BrokenKis:
    """kis_api 모듈이 이 머신에 없는 상태."""

    def get_access_token(self):
        raise ImportError("no kis_api")

    def get_investor_trend(self, code, token):
        raise ImportError("no kis_api")


def kis_adapter(fake=None, attempts=3):
    return export_data.KISFlow(api=fake or FakeKis(), sleep=lambda s: None, attempts=attempts)


def flows_with_date(tmp_path, date=ASOF, name="flows.json"):
    path = tmp_path / name
    write_json(str(path), {"updated": date,
                           "flows": {t[0]: {date: {"f": -5, "i": 7, "p": -2}} for t in TICKERS}})
    return str(path)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(runstatus, "STATE", str(tmp_path / "status.json"))
    monkeypatch.setattr(export_data, "read_prices", FakeReader(price_frames()))
    return {"tmp": tmp_path}


def build(env, kis=None, flows_path=None, frames=None):
    return export_data.build(out_dir=str(env["tmp"] / "out"), kis=kis,
                             flows_path=flows_path or str(env["tmp"] / "none.json"),
                             sleep=lambda s: None, log=lambda *a: None)


def test_flow_is_taken_from_flows_json_without_any_kis_call(env):
    """원장에 그 날짜 행이 있으면 KIS를 부르지 않는다(사이트·장부가 같은 값을 갖는다)."""
    fake = FakeKis()
    summary = build(env, kis=kis_adapter(fake), flows_path=flows_with_date(env["tmp"]))
    doc = json.load(open(env["tmp"] / "out" / "stocks.json"))
    assert summary["flow_status"]["status"] == "ok"
    assert all(s["flow"] and s["flow"]["source"] == "flows.json"
               for s in doc["stocks"].values())
    assert doc["stocks"]["278280"]["flow"]["foreign_net"] == -5
    assert fake.tokens == 0 and fake.calls == 0


def test_kis_token_is_minted_once_for_all_tickers(env):
    """원장이 비어 있을 때 KIS 폴백: 토큰은 실행당 1회만(27회 발급 시도 금지)."""
    fake = FakeKis()
    summary = build(env, kis=kis_adapter(fake))
    assert summary["flow_status"]["status"] == "ok"
    assert summary["flow_status"]["sources"]["kis"] == 27
    assert fake.tokens == 1
    assert fake.calls == 27


def test_rate_limit_is_retried_with_backoff(env):
    """일시적 429는 재시도·백오프로 넘긴다(조용한 null 금지)."""
    sleeps = []
    kis = export_data.KISFlow(api=FakeKis(fail_times=1), sleep=sleeps.append)
    assert kis.get("005930")["foreign_net"] == 1
    assert sleeps and sleeps[0] > 0


def test_persistent_failure_is_recorded_not_swallowed(env):
    """끝까지 실패하면 사유가 상태 파일과 flow_status에 남는다."""
    summary = build(env, kis=kis_adapter(FakeKis(fail={"005930"})))
    fs = summary["flow_status"]
    assert fs["status"] == "partial"
    assert "005930" in fs["failures"] and "1분" in fs["failures"]["005930"]
    status = json.load(open(env["tmp"] / "status.json"))
    assert status["steps"]["export_flows"]["status"] == "failed"
    assert "1분" in status["steps"]["export_flows"]["reason"]


def test_missing_kis_is_reported_as_unavailable(env):
    """이 머신에 KIS가 없는 경우와 조회 실패를 구분한다(정직성 규칙)."""
    summary = build(env, kis=kis_adapter(BrokenKis(), attempts=1))
    fs = summary["flow_status"]
    assert fs["status"] == "unavailable" and fs["covered"] == 0
    assert "kis_api" in fs["reason"]


def test_flow_rows_for_other_dates_are_not_borrowed(env):
    """다른 날짜 수급을 오늘 값처럼 붙이지 않는다(없는 데이터를 추측하지 않는다)."""
    summary = build(env, kis=kis_adapter(FakeKis()),
                    flows_path=flows_with_date(env["tmp"], date="2026-11-12",
                                               name="flows_prev.json"))
    assert summary["flow_status"]["sources"]["kis"] == 27      # KIS 폴백을 썼다
    doc = json.load(open(env["tmp"] / "out" / "stocks.json"))
    assert all(s["flow"]["source"] == "kis" for s in doc["stocks"].values())


def test_export_writes_three_files_and_marks_stale(env):
    frames = price_frames()
    frames["399720"] = frames["399720"].iloc[:-1]        # 한 종목만 하루 뒤처짐(휴장·피드 지연)
    env["reader"] = FakeReader(frames)
    export_data.read_prices = env["reader"]
    summary = build(env, kis=kis_adapter(FakeKis()))
    doc = json.load(open(env["tmp"] / "out" / "stocks.json"))
    assert doc["stocks"]["399720"]["stale"] is True
    assert doc["stocks"]["005930"]["stale"] is False
    assert summary["stale"] == ["399720"]
    for name in ("stocks", "sectors", "market"):
        assert (env["tmp"] / "out" / f"{name}.json").exists()


def test_export_aborts_when_too_few_tickers(env, monkeypatch):
    frames = price_frames()
    keep = {"KS11", "KQ11", "005930"}

    def reader(sym):
        if sym not in keep:
            raise RuntimeError("boom")
        return frames[sym]

    monkeypatch.setattr(export_data, "read_prices", reader)
    with pytest.raises(SystemExit, match="export aborted"):
        build(env)
    status = json.load(open(env["tmp"] / "status.json"))
    assert status["steps"]["export"]["status"] == "failed"


def test_status_records_export_metadata(env):
    build(env, kis=kis_adapter(FakeKis()), flows_path=flows_with_date(env["tmp"]))
    status = json.load(open(env["tmp"] / "status.json"))
    assert status["steps"]["export"]["status"] == "ok"
    assert status["steps"]["export"]["extra"]["asof"] == ASOF
    assert status["steps"]["export_flows"]["status"] == "ok"
    assert status["steps"]["export_flows"]["extra"]["covered"] == 27


def test_token_failure_does_not_retry_per_ticker(env):
    """ 토큰 발급이 실패하면 종목마다 재시도하지 않는다(11-13 사고의 증폭 경로 차단)."""

    class NoToken(FakeKis):
        def get_access_token(self):
            self.tokens += 1
            raise RuntimeError("EGW00133: 접근토큰 발급 간격이 1분 이하입니다")

    fake = NoToken()
    summary = build(env, kis=kis_adapter(fake))
    assert fake.tokens == 1 and fake.calls == 0
    fs = summary["flow_status"]
    assert fs["status"] == "failed" and fs["covered"] == 0
    assert "1분" in fs["reason"] and len(fs["failures"]) == 27
