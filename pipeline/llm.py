"""영어 해설 생성: 1순위 Gemini, 폴백 Ollama(미니), 둘 다 실패 시 None.

키: GEMINI_API_KEY (run_daily.sh가 kr-screener .env의 GEMINI_FREE_API_KEY에서 주입.
    GOOGLE_API_KEY는 2026-08-30 실측 INVALID — 사용 금지)
모델: gemini-flash-latest (상시 최신 별칭 — 2026-08-30 실조회로 확정,
     gemini-2.0-flash는 퇴역 404)

실패는 조용히 삼키지 않는다: `analyze_detail()`이 실패 사유를 문자열로 돌려주고,
`analyze()`는 마지막 실패를 LAST_ERROR에 남긴다. 호출한 쪽(gen_deep_dive/gen_weekly)은
그 사유를 상태 파일에 기록하고 종료 코드를 0이 아니게 준다.
"""
import os
import time

RETRY_STATUS = ("429", "quota", "exhaust", "rate")
LAST_ERROR = {"provider": None, "error": None, "at": None}


def _sleep(n):
    time.sleep(n)


def _backoff_seconds(attempt):
    """무료티어 분당 쿼터(429) 대기. CNC_LLM_BACKOFF로 조정(테스트는 0으로)."""
    base = float(os.environ.get("CNC_LLM_BACKOFF", "50"))
    return base * (attempt + 1)


def _gemini(prompt, attempts=3, genai=None):
    if genai is None:
        import google.generativeai as genai       # 선택 의존성 — 호출 시점 로드
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("CNC_GEMINI_MODEL", "gemini-flash-latest")
    last = None
    for attempt in range(attempts):
        try:
            return genai.GenerativeModel(model).generate_content(prompt).text
        except Exception as e:
            last = e
            s = str(e).lower()
            if attempt + 1 < attempts and any(k in s for k in RETRY_STATUS):
                _sleep(_backoff_seconds(attempt))
                continue
            raise
    raise last or RuntimeError("gemini failed")


def _ollama(prompt):
    import requests                      # 미니에만 있는 선택 의존성 — import 시점에 요구하지 않는다
    r = requests.post(
        "http://192.168.10.1:11434/api/generate", timeout=600,
        json={"model": os.environ.get("CNC_OLLAMA_MODEL", "qwen3.5:latest"),
              "prompt": prompt, "stream": False})
    d = r.json()
    if not d.get("done") or not d.get("response"):
        return None
    return d["response"]


def analyze_detail(prompt):
    """(text|None, provider|None, error|None). 실패 사유를 잃지 않는다."""
    errors = []
    try:
        out = _gemini(prompt)
        if out and out.strip():
            return out, "gemini", None
        errors.append("gemini: empty response")
    except Exception as e:
        errors.append(f"gemini: {e.__class__.__name__}: {e}")
    try:
        out = _ollama(prompt)
        if out and out.strip():
            return out, "ollama", None
        errors.append("ollama: empty response")
    except Exception as e:
        errors.append(f"ollama: {e.__class__.__name__}: {e}")
    return None, None, " | ".join(errors)


def analyze(prompt):
    text, provider, error = analyze_detail(prompt)
    LAST_ERROR.update({"provider": provider, "error": error,
                       "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    if not text:
        print(f"  ⚠️ LLM failed: {error}")
    return text
