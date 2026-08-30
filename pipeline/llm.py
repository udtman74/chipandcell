"""영어 해설 생성: 1순위 Gemini, 폴백 Ollama(미니), 둘 다 실패 시 None."""
import os

import requests


def analyze(prompt):
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        return genai.GenerativeModel("gemini-2.0-flash").generate_content(prompt).text
    except Exception:
        pass
    try:
        r = requests.post(
            "http://192.168.10.1:11434/api/generate", timeout=600,
            json={"model": os.environ.get("CNC_OLLAMA_MODEL", "qwen3.5:latest"),
                  "prompt": prompt, "stream": False})
        return r.json()["response"]
    except Exception:
        return None
