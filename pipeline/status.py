"""단계별 실행 상태 기록 — 실패가 조용히 지나가지 않게 하는 단일 창구.

2026-11-15 이전에는 gen_deep_dive/gen_weekly가 LLM 실패 시 그냥 return 하고
run_daily.sh가 `|| echo`로 흘려보내, 2주간 평일 6일 심층 글과 주간 리뷰 2회가
아무 표시 없이 누락됐다. 이 모듈은 그 사실을 파일로 남긴다.

- `pipeline/state/status.json` (gitignore): 배치 머신의 최근 상태.
- 호출한 쪽은 상태와 무관하게 예외 없이 진행하되, 실패 시 종료 코드를 0이 아니게 준다.

블로그 관련 텔레그램/외부 알림은 설계상 금지이므로 여기서도 외부 전송은 하지 않는다.
"""
import json
import os
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(_DIR, "state", "status.json")

KEEP_STEPS = 40          # 오래된 단계 기록은 잘라낸다


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load(path=None):
    path = path or STATE
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"updated": "", "steps": {}}


def save(doc, path=None, now=None):
    path = path or STATE
    doc["updated"] = now or _now()
    steps = doc.get("steps", {})
    if len(steps) > KEEP_STEPS:
        for key in sorted(steps, key=lambda k: steps[k].get("at", ""))[:len(steps) - KEEP_STEPS]:
            steps.pop(key, None)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return doc


def record(step, status, reason=None, extra=None, path=None, now=None):
    """단계 상태 1건 기록. status: ok | skipped | failed.

    기록 실패(권한·디스크)는 배치를 멈추지 않는다 — 다만 조용하지도 않게 출력한다.
    """
    doc = load(path)
    entry = {"status": status, "reason": reason, "at": now or _now(), "date": (now or _now())[:10]}
    if extra:
        entry["extra"] = extra
    doc.setdefault("steps", {})[step] = entry
    try:
        save(doc, path=path, now=now)
    except Exception as e:                        # 상태 기록 실패로 배치를 죽이지는 않는다
        print(f"  ⚠️ status 기록 실패 {step}: {e!r}")
    return entry


def failures(doc):
    """실패한 단계만 추린다. {step: reason}"""
    steps = (doc or {}).get("steps", {})
    return {k: v.get("reason") for k, v in steps.items() if v.get("status") == "failed"}
