"""글 생성 실패 감지 테스트 — 2주간 평일 6일 심층 글·주간 리뷰 2회 무표시 누락 방지.

핵심: LLM이 실패하면 (1) 상태 파일에 사유가 남고 (2) 종료 코드가 0이 아니어야 한다.
블로그 관련 텔레그램/외부 알림은 설계상 금지이므로 여기서도 외부 전송은 검증하지 않는다.
"""
import json
from datetime import datetime

import pytest

from pipeline import gen_deep_dive, gen_weekly
from pipeline import status as runstatus
from pipeline.tests.conftest import (ASOF, market_doc, read, sectors_doc, stocks_doc,
                                     write_json)


def ok_llm(text="Analyst note body."):
    def _call(prompt):
        return text, "gemini", None
    return _call


def fail_llm(reason="gemini: RuntimeError: 429 quota | ollama: ConnectionError: refused"):
    def _call(prompt):
        return None, None, reason
    return _call


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(runstatus, "STATE", str(tmp_path / "status.json"))
    data_dir = tmp_path / "data"
    posts = tmp_path / "posts"
    posts.mkdir()
    doc = stocks_doc()
    write_json(str(data_dir / "stocks.json"), doc)
    write_json(str(data_dir / "sectors.json"), sectors_doc(doc))
    write_json(str(data_dir / "market.json"), market_doc())
    return {"data": str(data_dir), "posts": str(posts), "tmp": tmp_path, "doc": doc}


def test_deep_dive_failure_records_status_and_exits_nonzero(data):
    with pytest.raises(SystemExit) as exc:
        gen_deep_dive.run(ticker="005930", today=ASOF, data_dir=data["data"],
                          posts_dir=data["posts"], state_path=str(data["tmp"] / "rot.json"),
                          llm=fail_llm(), status_path=str(data["tmp"] / "status.json"))
    assert exc.value.code == 1
    st = read(data["tmp"] / "status.json")["steps"]["gen_deep_dive"]
    assert st["status"] == "failed" and "429" in st["reason"]
    assert list((data["tmp"] / "posts").iterdir()) == []


def test_deep_dive_success_writes_post_and_status(data):
    gen_deep_dive.run(ticker="005930", today=ASOF, data_dir=data["data"],
                      posts_dir=data["posts"], state_path=str(data["tmp"] / "rot.json"),
                      llm=ok_llm(), status_path=str(data["tmp"] / "status.json"))
    post = data["tmp"] / "posts" / f"{ASOF}-samsung-electronics.md"
    assert post.exists()
    body = post.read_text()
    assert "Analyst note body." in body and "20-day" in body
    st = read(data["tmp"] / "status.json")["steps"]["gen_deep_dive"]
    assert st["status"] == "ok" and st["extra"]["provider"] == "gemini"


def test_deep_dive_existing_post_is_skipped_not_failed(data):
    (data["tmp"] / "posts" / f"{ASOF}-samsung-electronics.md").write_text("existing")
    gen_deep_dive.run(ticker="005930", today=ASOF, data_dir=data["data"],
                      posts_dir=data["posts"], state_path=str(data["tmp"] / "rot.json"),
                      llm=ok_llm(), status_path=str(data["tmp"] / "status.json"))
    st = read(data["tmp"] / "status.json")["steps"]["gen_deep_dive"]
    assert st["status"] == "skipped"


def test_weekly_failure_on_friday_exits_nonzero(data):
    friday = datetime(2026, 11, 13)
    with pytest.raises(SystemExit) as exc:
        gen_weekly.run(today=friday, data_dir=data["data"], posts_dir=data["posts"],
                       llm=fail_llm(), status_path=str(data["tmp"] / "status.json"))
    assert exc.value.code == 1
    st = read(data["tmp"] / "status.json")["steps"]["gen_weekly"]
    assert st["status"] == "failed" and "429" in st["reason"]


def test_weekly_not_friday_is_normal_noop(data):
    gen_weekly.run(today=datetime(2026, 11, 15), data_dir=data["data"],
                   posts_dir=data["posts"], llm=ok_llm(),
                   status_path=str(data["tmp"] / "status.json"))
    st = read(data["tmp"] / "status.json")["steps"]["gen_weekly"]
    assert st["status"] == "skipped"


def test_weekly_success_writes_post(data):
    gen_weekly.run(today=datetime(2026, 11, 13), data_dir=data["data"],
                   posts_dir=data["posts"], llm=ok_llm(),
                   status_path=str(data["tmp"] / "status.json"))
    post = data["tmp"] / "posts" / "2026-11-13-weekly-review.md"
    assert post.exists() and "Weekly" in post.read_text()
    assert read(data["tmp"] / "status.json")["steps"]["gen_weekly"]["status"] == "ok"


def test_status_failures_helper_lists_failed_steps(tmp_path):
    runstatus.record("a", "ok", path=str(tmp_path / "s.json"), now="2026-11-13 18:10:00")
    runstatus.record("b", "failed", reason="boom", path=str(tmp_path / "s.json"),
                     now="2026-11-13 18:10:01")
    doc = runstatus.load(str(tmp_path / "s.json"))
    assert runstatus.failures(doc) == {"b": "boom"}
    assert json.dumps(doc) and doc["updated"] == "2026-11-13 18:10:01"
