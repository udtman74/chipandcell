"""llm 실패 사유 전달 테스트 — 조용한 실패(2026-11) 재발 방지."""
import pytest

from pipeline import llm


class FakeGenai:
    """google.generativeai 대역: 429를 정해진 횟수만큼 던진 뒤 성공."""

    def __init__(self, fail_times=0, exc="429 quota exceeded"):
        self.fail_times = fail_times
        self.calls = 0
        self.exc = exc

    def configure(self, api_key=None):
        self.key = api_key

    def GenerativeModel(self, model):                # noqa: N802 (실제 SDK 이름)
        outer = self

        class Model:
            def generate_content(self, prompt):
                outer.calls += 1
                if outer.calls <= outer.fail_times:
                    raise RuntimeError(outer.exc)

                class R:
                    text = "analysis text"
                return R()
        return Model()


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CNC_LLM_BACKOFF", "0")


def test_gemini_success_returns_text_and_provider(monkeypatch):
    monkeypatch.setattr(llm, "_gemini", lambda p: "ok text")
    monkeypatch.setattr(llm, "_ollama", lambda p: pytest.fail("ollama를 부르면 안 된다"))
    assert llm.analyze_detail("p") == ("ok text", "gemini", None)


def test_gemini_429_is_retried_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm, "_sleep", sleeps.append)
    fake = FakeGenai(fail_times=2)
    assert llm._gemini("p", genai=fake) == "analysis text"
    assert fake.calls == 3 and len(sleeps) == 2 and sleeps[0] >= 0


def test_gemini_non_retryable_error_falls_back_to_ollama(monkeypatch):
    def boom(p):
        raise RuntimeError("400 INVALID_ARGUMENT")
    monkeypatch.setattr(llm, "_gemini", boom)
    monkeypatch.setattr(llm, "_ollama", lambda p: "ollama text")
    assert llm.analyze_detail("p") == ("ollama text", "ollama", None)


def test_both_fail_returns_reason_not_silence(monkeypatch):
    def boom_g(p):
        raise RuntimeError("gemini down")
    monkeypatch.setattr(llm, "_gemini", boom_g)

    def boom_o(p):
        raise ConnectionError("ollama unreachable")
    monkeypatch.setattr(llm, "_ollama", boom_o)
    text, provider, error = llm.analyze_detail("p")
    assert text is None and provider is None
    assert "gemini down" in error and "ollama unreachable" in error


def test_analyze_records_last_error(monkeypatch):
    monkeypatch.setattr(llm, "_gemini", lambda p: None)
    monkeypatch.setattr(llm, "_ollama", lambda p: None)
    assert llm.analyze("p") is None
    assert "empty response" in llm.LAST_ERROR["error"]


def test_backoff_grows_and_is_configurable(monkeypatch):
    monkeypatch.setenv("CNC_LLM_BACKOFF", "10")
    assert llm._backoff_seconds(0) < llm._backoff_seconds(1)
    assert llm._backoff_seconds(0) == 10
