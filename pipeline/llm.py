"""영어 해설 생성: 1순위 Gemini, 폴백 Ollama(미니), 둘 다 실패 시 None.

키: GEMINI_API_KEY (run_daily.sh가 kr-screener .env의 GEMINI_FREE_API_KEY에서 주입.
    GOOGLE_API_KEY는 2026-08-30 실측 INVALID — 사용 금지)
모델: gemini-flash-latest (상시 최신 별칭 — 2026-08-30 실조회로 확정,
     gemini-2.0-flash는 퇴역 404)
"""
import os

import requests


def _gemini(prompt):
    import time
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("CNC_GEMINI_MODEL", "gemini-flash-latest")
    for attempt in range(3):
        try:
            return genai.GenerativeModel(model).generate_content(prompt).text
        except Exception as e:
            s = str(e)
            # 무료티어 분당쿼터(429) — 대기 후 재시도
            if attempt < 2 and ("429" in s or "quota" in s.lower() or "exhaust" in s.lower()):
                time.sleep(50)
                continue
            raise
    return None


def _ollama(prompt):
    r = requests.post(
        "http://192.168.10.1:11434/api/generate", timeout=600,
        json={"model": os.environ.get("CNC_OLLAMA_MODEL", "qwen3.5:latest"),
              "prompt": prompt, "stream": False})
    d = r.json()
    if not d.get("done") or not d.get("response"):
        return None
    return d["response"]


def analyze(prompt):
    try:
        out = _gemini(prompt)
        if out and out.strip():
            return out
    except Exception:
        pass
    try:
        return _ollama(prompt)
    except Exception:
        return None
