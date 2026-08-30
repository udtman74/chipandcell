# Chip & Cell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 한국 반도체·배터리 특화 영어 사이트 chipandcell.com — 데이터 페이지 30개(매일 자동 갱신) + 심층 글(일 1건) + 주간 리뷰, 미니 launchd 자동 운영, 구 EN 블로그 동결.

**Architecture:** Astro 5 정적 사이트(site/, lifelaw 패턴) + Python 파이프라인(pipeline/, fdr·kis_api로 데이터 수집 → JSON/마크다운 생성). 배포는 GitHub push → Vercel Git 연동 자동 빌드. 일일 잡은 미니 launchd(18:10)에서 export→gen→commit→push만 수행.

**Tech Stack:** Astro 5 + @astrojs/sitemap, Python 3(FinanceDataReader, requests), Gemini(폴백 Ollama), launchd, Vercel.

**Spec:** `docs/superpowers/specs/2026-08-30-chipandcell-design.md`

## Global Constraints

- 언어: 사이트 표기 전부 영어. 모든 페이지 푸터에 "Not investment advice. Data may contain errors." 고지.
- 커밋 author: `udtman74 <260236632+udtman74@users.noreply.github.com>` (Vercel seatBlock 규칙). 리포 git config로 이미 고정됨.
- 데이터 페이지 URL 고정: `/stocks/<code>/` — 날짜 기반 URL 금지(scaled-content 회피).
- 파이프라인은 kr-screener 코드 수정 금지(읽기 전용 참조도 최소화 — fdr/kis_api 직접 사용). 예외: Task 10의 구 블로그 동결은 kr-screener 수정임(별도 커밋).
- 로그: 일일 잡 stdout/stderr 전체 보존(`/dev/null` 리다이렉트 금지). 실패 시 텔레그램 발송 금지(블로그 규칙) — 로그만.
- 모든 fact(종목코드·회사명)는 fdr 실조회로 검증(추정 금지).
- 작업 완료 시 실제 실행으로 실증(빌드·라이브 URL 200 확인).

---

### Task 1: 리포 뼈대 + 종목 SSOT + 코드 검증

**Files:**
- Create: `pipeline/tickers.py`, `pipeline/__init__.py`, `pipeline/tests/test_tickers.py`, `.gitignore`, `README.md`

**Interfaces:**
- Produces: `pipeline.tickers.TICKERS: list[tuple[str, str, str, str]]` = (code, name_en, name_kr, sector) 27건, sector ∈ {"semiconductor","battery"}; `SECTOR_LABELS = {"semiconductor": "Semiconductor", "battery": "Battery"}`

- [ ] **Step 1: tickers.py 작성** — 스펙의 27종목. name_en은 일반 영문 표기:

```python
# pipeline/tickers.py
"""Chip & Cell 커버리지 종목 SSOT. (code, name_en, name_kr, sector)"""
SEMI = [
    ("005930", "Samsung Electronics", "삼성전자"),
    ("000660", "SK Hynix", "SK하이닉스"),
    ("042700", "Hanmi Semiconductor", "한미반도체"),
    ("403870", "HPSP", "HPSP"),
    ("039030", "EO Technics", "이오테크닉스"),
    ("058470", "Leeno Industrial", "리노공업"),
    ("240810", "Wonik IPS", "원익IPS"),
    ("036930", "Jusung Engineering", "주성엔지니어링"),
    ("000990", "DB HiTek", "DB하이텍"),
    ("357780", "Soulbrain", "솔브레인"),
    ("005290", "Dongjin Semichem", "동진쎄미켐"),
    ("064760", "TCK", "티씨케이"),
    ("067310", "Hana Micron", "하나마이크론"),
    ("095340", "ISC", "ISC"),
    ("399720", "Gaonchips", "가온칩스"),
]
BATT = [
    ("373220", "LG Energy Solution", "LG에너지솔루션"),
    ("006400", "Samsung SDI", "삼성SDI"),
    ("096770", "SK Innovation", "SK이노베이션"),
    ("247540", "EcoPro BM", "에코프로비엠"),
    ("086520", "EcoPro", "에코프로"),
    ("003670", "POSCO Future M", "포스코퓨처엠"),
    ("066970", "L&F", "엘앤에프"),
    ("005070", "Cosmo AM&T", "코스모신소재"),
    ("011790", "SKC", "SKC"),
    ("020150", "Lotte Energy Materials", "롯데에너지머티리얼즈"),
    ("121600", "Nano Materials", "나노신소재"),
    ("278280", "Chunbo", "천보"),
]
TICKERS = [(c, en, kr, "semiconductor") for c, en, kr in SEMI] + \
          [(c, en, kr, "battery") for c, en, kr in BATT]
SECTOR_LABELS = {"semiconductor": "Semiconductor", "battery": "Battery"}
```

- [ ] **Step 2: 검증 테스트 작성** (`pipeline/tests/test_tickers.py`):

```python
import re
from pipeline.tickers import TICKERS, SEMI, BATT

def test_counts():
    assert len(SEMI) == 15 and len(BATT) == 12 and len(TICKERS) == 27

def test_codes_unique_and_valid():
    codes = [t[0] for t in TICKERS]
    assert len(set(codes)) == 27
    assert all(re.fullmatch(r"\d{6}", c) for c in codes)
```

- [ ] **Step 3: 실데이터 코드 검증** — fdr KRX 리스팅과 대조하는 일회성 스크립트 실행(테스트 아님, 네트워크):

```bash
python3 - <<'EOF'
import FinanceDataReader as fdr
from pipeline.tickers import TICKERS
krx = fdr.StockListing("KRX").set_index("Code")["Name"].to_dict()
for code, en, kr, sec in TICKERS:
    assert code in krx, f"{code} not in KRX"
    print(code, krx[code], "==", kr, "OK" if krx[code] == kr else "<<CHECK>>")
EOF
```
`<<CHECK>>` 표기 종목은 name_kr을 KRX 정식 명칭으로 수정 후 재실행 전건 OK.

- [ ] **Step 4: pytest 통과 확인** — `cd ~/chipandcell && python3 -m pytest pipeline/tests -q` → 2 passed
- [ ] **Step 5: .gitignore(`node_modules/`, `dist/`, `__pycache__/`, `.vercel/`, `pipeline/state/`, `logs/`) + README 한 단락 작성, 커밋** `feat: 커버리지 종목 SSOT 27건 (KRX 검증)`

---

### Task 2: export_data.py — 데이터 페이지 재료 생성

**Files:**
- Create: `pipeline/export_data.py`, `pipeline/metrics.py`, `pipeline/tests/test_metrics.py`

**Interfaces:**
- Consumes: `pipeline.tickers.TICKERS`
- Produces: `site/src/data/stocks.json`, `site/src/data/sectors.json`, `site/src/data/market.json`. 스키마:
  - stocks.json: `{"asof": "YYYY-MM-DD", "stocks": {code: {"name_en","name_kr","sector","close","pct","value_bil","hi52","lo52","pos52","ma20","ma60","r5","r20","r60","flow": {"foreign_net","inst_net","individual_net"}|null}}}`
  - sectors.json: `{"asof", "sectors": {sector: {"label","median_r20","advancers","decliners","top": [code,...3], "bottom": [code,...3]}}}`
  - market.json: `{"asof", "kospi": {"close","pct","r20"}, "kosdaq": {...}}`
  - CLI: `python3 -m pipeline.export_data` (미니/에어 공용, kis 실패 시 flow=null)

- [ ] **Step 1: metrics 단위 테스트 작성** (`pipeline/tests/test_metrics.py`) — 고정 DataFrame으로:

```python
import pandas as pd, numpy as np
from pipeline.metrics import compute

def _df(closes):
    idx = pd.bdate_range("2025-01-01", periods=len(closes))
    return pd.DataFrame({"Close": closes, "Volume": [1000]*len(closes)}, index=idx)

def test_compute_basic():
    m = compute(_df(list(range(100, 400))))  # 단조 상승 300일
    assert m["close"] == 399 and m["pos52"] == 100.0
    assert m["ma20"] == np.mean(range(380, 400))
    assert round(m["r5"], 2) == round((399/394 - 1) * 100, 2)
```

- [ ] **Step 2: 실패 확인** `python3 -m pytest pipeline/tests/test_metrics.py -q` → FAIL (no module)
- [ ] **Step 3: metrics.py 구현**:

```python
# pipeline/metrics.py
"""OHLCV DataFrame(fdr 형식) → 지표 dict. 52주=252거래일 근사."""
def compute(df):
    df = df.dropna(subset=["Close"]).tail(300)
    c = df["Close"]
    close = float(c.iloc[-1]); prev = float(c.iloc[-2])
    y = c.tail(252)
    hi52, lo52 = float(y.max()), float(y.min())
    def _r(n):
        return float((close / c.iloc[-1 - n] - 1) * 100) if len(c) > n else None
    return {
        "close": close,
        "pct": round((close / prev - 1) * 100, 2),
        "value_bil": round(close * float(df["Volume"].iloc[-1]) / 1e9, 1),
        "hi52": hi52, "lo52": lo52,
        "pos52": round((close - lo52) / (hi52 - lo52) * 100, 1) if hi52 > lo52 else 50.0,
        "ma20": float(c.tail(20).mean()), "ma60": float(c.tail(60).mean()),
        "r5": _r(5), "r20": _r(20), "r60": _r(60),
        "date": df.index[-1].strftime("%Y-%m-%d"),
    }
```

- [ ] **Step 4: 테스트 통과 확인** → PASS
- [ ] **Step 5: export_data.py 구현** — fdr 조회+수급(선택)+집계+JSON 기록:

```python
# pipeline/export_data.py
"""일일 데이터 export: fdr(시세)+kis_api(수급, 미니에서만) → site/src/data/*.json"""
import json, os, sys, time
import FinanceDataReader as fdr
from pipeline.tickers import TICKERS, SECTOR_LABELS
from pipeline.metrics import compute

OUT = os.path.join(os.path.dirname(__file__), "..", "site", "src", "data")

def _flow(code):
    """외인/기관 수급. kr-screener kis_api가 있는 머신(미니)에서만 동작, 실패 시 None."""
    try:
        sys.path.insert(0, os.path.expanduser("~/kr-stock-screener"))
        from kis_api import get_access_token, get_investor_trend
        token = get_access_token()
        inv = get_investor_trend(code, token) if token else {}
        return {k: inv[k] for k in ("foreign_net", "inst_net", "individual_net") if k in inv} or None
    except Exception:
        return None

def run():
    stocks, fails = {}, []
    for code, en, kr, sec in TICKERS:
        try:
            m = compute(fdr.DataReader(code))
            m.update(name_en=en, name_kr=kr, sector=sec, flow=_flow(code))
            stocks[code] = m
            time.sleep(0.3)
        except Exception as e:
            fails.append((code, repr(e)))
    if len(stocks) < 20:
        raise SystemExit(f"export aborted: only {len(stocks)}/27 fetched; fails={fails}")
    asof = max(s["date"] for s in stocks.values())
    sectors = {}
    for sec, label in SECTOR_LABELS.items():
        rows = {c: s for c, s in stocks.items() if s["sector"] == sec and s["r20"] is not None}
        rank = sorted(rows, key=lambda c: rows[c]["r20"], reverse=True)
        med = sorted(r["r20"] for r in rows.values())[len(rows) // 2]
        sectors[sec] = {"label": label, "median_r20": round(med, 2),
                        "advancers": sum(1 for r in rows.values() if r["pct"] > 0),
                        "decliners": sum(1 for r in rows.values() if r["pct"] < 0),
                        "top": rank[:3], "bottom": rank[-3:]}
    market = {}
    for key, sym in (("kospi", "KS11"), ("kosdaq", "KQ11")):
        m = compute(fdr.DataReader(sym))
        market[key] = {"close": m["close"], "pct": m["pct"], "r20": m["r20"]}
    os.makedirs(OUT, exist_ok=True)
    for name, payload in (("stocks", {"asof": asof, "stocks": stocks}),
                          ("sectors", {"asof": asof, "sectors": sectors}),
                          ("market", {"asof": asof, **market})):
        with open(os.path.join(OUT, f"{name}.json"), "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"export OK asof={asof} stocks={len(stocks)} fails={fails}")

if __name__ == "__main__":
    run()
```

- [ ] **Step 6: 실행 실증(에어)** — `python3 -m pipeline.export_data` → `export OK asof=... stocks=27` + 3개 JSON 생성·값 스팟체크(삼성전자 close가 실제 종가와 일치)
- [ ] **Step 7: 커밋** `feat: 일일 데이터 export 파이프라인 (fdr+kis, 27종목)`

---

### Task 3: Astro 사이트 뼈대 + 데이터 페이지

**Files:**
- Create: `site/package.json`, `site/astro.config.mjs`, `site/src/layouts/Base.astro`, `site/src/lib/fmt.js`, `site/src/pages/index.astro`, `site/src/pages/stocks/[code].astro`, `site/src/pages/semiconductor.astro`, `site/src/pages/battery.astro`, `site/src/pages/market.astro`, `site/src/pages/about.astro`, `site/src/pages/methodology.astro`, `site/public/robots.txt`

**Interfaces:**
- Consumes: Task 2의 3개 JSON (`import stocks from "../data/stocks.json"`)
- Produces: 정적 페이지 33개(index, 종목 27, 섹터 2, market, about, methodology). Base.astro는 `title`, `description` props.

- [ ] **Step 1: 스캐폴드** — lifelaw와 동일 구성:

```bash
cd ~/chipandcell/site
cat > package.json <<'EOF'
{ "name": "chipandcell", "type": "module", "version": "1.0.0", "private": true,
  "scripts": { "dev": "astro dev", "build": "astro build", "preview": "astro preview" },
  "dependencies": { "astro": "^5.1.0", "@astrojs/sitemap": "^3.2.0", "@astrojs/rss": "^4.0.0" } }
EOF
cat > astro.config.mjs <<'EOF'
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
export default defineConfig({
  site: "https://chipandcell.com",
  integrations: [sitemap()],
  build: { format: "directory" },
});
EOF
npm install
```

- [ ] **Step 2: Base.astro** — 헤더(로고 "Chip & Cell" + 태그라인 + nav: Semiconductor/Battery/Market/Posts/About), 푸터 고지("Chip & Cell is an automated data & research site. Not investment advice. Data may contain errors. Sources: KRX market data."), 시스템 폰트, 라이트/다크 `prefers-color-scheme` 토큰, 반응형 max-width 960px. `<html lang="en">`.
- [ ] **Step 3: fmt.js** — `won(n)` (₩ 천단위), `pct(n)` (+부호·소수2, 상승 빨강 `#d32f2f`/하락 파랑 `#1565c0` 클래스 반환 — 한국 관례 유지하되 methodology에 명시), `bil(n)`.
- [ ] **Step 4: 종목 페이지** `site/src/pages/stocks/[code].astro`:

```astro
---
import Base from "../../layouts/Base.astro";
import data from "../../data/stocks.json";
import { won, pct } from "../../lib/fmt.js";
export function getStaticPaths() {
  return Object.keys(data.stocks).map((code) => ({ params: { code } }));
}
const { code } = Astro.params;
const s = data.stocks[code];
const title = `${s.name_en} (${code}) Stock Data — Price, 52-Week Range, Investor Flows`;
---
<Base title={title} description={`Daily updated data for ${s.name_en}: price, moving averages, 52-week position, foreign/institutional flows. Korean ${s.sector} sector.`}>
  <h1>{s.name_en} <span class="code">KRX {code}</span></h1>
  <p class="asof">As of {s.date} (KST close)</p>
  <!-- 표: Close/Change/Value/52w position(막대)/MA20·MA60/r5·r20·r60 -->
  <!-- flow 있으면: Foreign/Institutional/Individual net (shares) 표 -->
  <!-- 섹터 내 r20 순위 한 줄 + 섹터 페이지 링크 -->
</Base>
```
주석 표기부는 실제 마크업으로 구현(표 2개+52주 위치 CSS 막대+순위 문장). 값 없는 항목(r60=null, flow=null)은 행 자체 생략.
- [ ] **Step 5: 섹터 페이지 2개** — sectors.json+stocks.json으로 정렬 테이블(전 종목: 이름 링크, close, pct, r20, pos52), 상단에 median_r20·advancers/decliners 요약 문장. semiconductor.astro/battery.astro는 공통 컴포넌트 `site/src/components/SectorTable.astro`로 DRY.
- [ ] **Step 6: index.astro** — 히어로(사이트 소개 2문장) + 두 섹터 카드(median_r20, top mover) + market 스냅샷 + 최근 글 5건 자리(Task 6 전까지 데이터 페이지 링크로 대체) + 전 종목 목록.
- [ ] **Step 7: market.astro / about.astro / methodology.astro** — market: KOSPI/KOSDAQ 표. about: 사이트 목적("focused coverage of Korea's two flagship export sectors"), 운영 방식 공개(automated data pipeline + editorial deep dives), 연락처는 도메인 메일 개통 전 생략. methodology: 데이터 출처(KRX via FinanceDataReader, KIS), 갱신 주기(daily after Seoul close), 색상 관례, 면책 전문.
- [ ] **Step 8: robots.txt** (`User-agent: *\nAllow: /\nSitemap: https://chipandcell.com/sitemap-index.xml`)
- [ ] **Step 9: 빌드 실증** — `npm run build` → dist에 33페이지 생성 확인(`find dist -name index.html | wc -l`), `npm run preview`로 종목 1·섹터 1·index 육안 확인(get_page_text 또는 curl)
- [ ] **Step 10: 커밋** `feat: Astro 사이트 뼈대 + 데이터 페이지 33개`

---

### Task 4: GitHub 리포 + Vercel 배포 라이브

**Files:** 없음(인프라 작업)

- [ ] **Step 1: GitHub 리포 생성·푸시**(에어, `source ~/.github.env`): `gh repo create chipandcell --public --source . --push`
- [ ] **Step 2: Vercel 프로젝트 생성** — 에어 vercel CLI: `cd site && vercel link` (신규 프로젝트 chipandcell, root=site) → `vercel deploy --prod`. 실패 시(토큰 부패 등) `vercel whoami`로 갱신 후 재시도.
- [ ] **Step 3: Git 연동** — `vercel git connect` 시도(Root Directory=site 설정 포함). CLI로 안 되면 Vercel 대시보드 1회 연결이 필요함을 보고하고, 임시로 CLI 배포 유지.
- [ ] **Step 4: 라이브 실증** — `curl -s -o /dev/null -w "%{http_code}" https://chipandcell.vercel.app/` → 200, 종목 페이지 1개도 200. 더미 커밋 푸시로 자동 배포 트리거 확인(git 연동 성공 시).
- [ ] **Step 5: 진행 보고** — 사용자에게 chipandcell.com 구매+Vercel 도메인 연결 안내(사용자 몫, 차단 아님)

---

### Task 5: Astro 콘텐츠 컬렉션(posts) + 목록·RSS

**Files:**
- Create: `site/src/content.config.ts`, `site/src/pages/posts/index.astro`, `site/src/pages/posts/[...slug].astro`, `site/src/pages/rss.xml.js`, 샘플 글 `site/src/content/posts/2026-08-30-welcome.md`

**Interfaces:**
- Produces: posts 컬렉션 frontmatter 스키마 `{title: string, date: date, description: string, ticker?: string, sector?: "semiconductor"|"battery"|"market", tags?: string[]}`. Task 6·7 생성기는 이 스키마의 마크다운을 `site/src/content/posts/YYYY-MM-DD-<slug>.md`로 기록.

- [ ] **Step 1: content.config.ts** (Astro 5 glob loader):

```ts
import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";
const posts = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/posts" }),
  schema: z.object({
    title: z.string(), date: z.coerce.date(), description: z.string(),
    ticker: z.string().optional(),
    sector: z.enum(["semiconductor", "battery", "market"]).optional(),
    tags: z.array(z.string()).default([]),
  }),
});
export const collections = { posts };
```

- [ ] **Step 2: 글 페이지** `[...slug].astro` — render(post), 상단 date·sector 뱃지, ticker 있으면 해당 `/stocks/<ticker>/` 데이터 페이지로 상호 링크, 하단 면책 한 줄. `posts/index.astro` = 날짜 역순 목록. index.astro 최근 글 5건 연결. rss.xml.js는 @astrojs/rss로 전 글.
- [ ] **Step 3: 샘플 글**(welcome — 사이트 소개·방법론 링크, 300단어 실문안 작성) 넣고 `npm run build` → posts 페이지 생성·RSS 유효 확인
- [ ] **Step 4: 커밋·푸시** `feat: posts 컬렉션 + 목록/RSS` → 자동 배포 확인

---

### Task 6: 심층 글 생성기 (일 1건)

**Files:**
- Create: `pipeline/llm.py`, `pipeline/gen_deep_dive.py`, `pipeline/tests/test_deep_dive.py`
- State: `pipeline/state/rotation.json` (gitignore됨)

**Interfaces:**
- Consumes: Task 2 JSON(당일 재료), Task 5 frontmatter 스키마
- Produces: CLI `python3 -m pipeline.gen_deep_dive` → `site/src/content/posts/YYYY-MM-DD-<name-slug>.md` 1건. `pick_target(stocks, state) -> code`, `render_post(code, stock, analysis) -> str`.

- [ ] **Step 1: pick_target 테스트 작성**:

```python
from pipeline.gen_deep_dive import pick_target

def test_event_priority():
    stocks = {"A": {"pct": 1.0}, "B": {"pct": -7.2}, "C": {"pct": 3.0}}
    assert pick_target(stocks, {"queue": ["A", "B", "C"]}) == "B"  # |pct|>=5 이벤트 우선

def test_rotation_when_quiet():
    stocks = {"A": {"pct": 1.0}, "B": {"pct": -2.0}}
    st = {"queue": ["B", "A"]}
    assert pick_target(stocks, st) == "B" and st["queue"] == ["A", "B"]  # 큐 회전
```

- [ ] **Step 2: FAIL 확인 → 구현**: 이벤트 임계 `abs(pct) >= 5.0`(복수면 |pct| 최대). 평시엔 큐 head 선택 후 tail로 회전(초기 큐=TICKERS 순서). state는 `pipeline/state/rotation.json`에 `{"queue": [...], "last_events": {code: "YYYY-MM-DD"}}` 저장, 같은 종목 이벤트 재선정은 7일 쿨다운.
- [ ] **Step 3: llm.py** — 영어 해설 생성. 1순위 Gemini(`google-generativeai`, env `GEMINI_API_KEY`, 모델 `gemini-2.0-flash`), 실패/키없음 시 Ollama(`http://192.168.10.1:11434/api/generate`, env `CNC_OLLAMA_MODEL` 기본 `qwen3`), 둘 다 실패 시 `None` 반환(글 생성 스킵하고 비정상 종료 아닌 로그만 — 데이터 페이지 갱신은 계속돼야 함):

```python
# pipeline/llm.py
import os, requests

def analyze(prompt):
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        return genai.GenerativeModel("gemini-2.0-flash").generate_content(prompt).text
    except Exception:
        pass
    try:
        r = requests.post("http://192.168.10.1:11434/api/generate", timeout=180,
                          json={"model": os.environ.get("CNC_OLLAMA_MODEL", "qwen3"),
                                "prompt": prompt, "stream": False})
        return r.json()["response"]
    except Exception:
        return None
```
Gemini 키는 미니 kr-screener 환경과 동일 env 사용(잡 plist에서 주입). 프롬프트: 종목 지표 표+수급+섹터 컨텍스트를 주고 "write a 500-700 word analyst-style note in English; no price targets, no buy/sell recommendation; end with risks section" — 덕담·일반론 금지 규칙 반영(구체 수치 인용 강제).
- [ ] **Step 4: render_post** — frontmatter(title=`{name_en} ({code}): {date} Deep Dive`, description 1문장, ticker, sector) + 본문(지표 요약 표는 마크다운 표로 파이프라인이 직접 생성, LLM 텍스트는 해설 섹션에만) + 고정 면책. analysis=None이면 파일 미생성·"skip" 로그.
- [ ] **Step 5: 실증(에어)** — 실행해 실제 글 1건 생성 → `npm run build` 통과 → 글 품질 육안 확인(수치 정확성: JSON과 대조) → 커밋 `feat: 심층 글 생성기(로테이션+이벤트 우선)`

---

### Task 7: 주간 섹터 리뷰 생성기 (금요일)

**Files:**
- Create: `pipeline/gen_weekly.py`

**Interfaces:**
- Consumes: Task 2 JSON, `pipeline.llm.analyze`
- Produces: 금요일에만 `site/src/content/posts/YYYY-MM-DD-weekly-review.md` (sector="market"). CLI `python3 -m pipeline.gen_weekly` — 금요일 아니면 즉시 정상 종료(코드 0, "not friday" 출력).

- [ ] **Step 1: 구현** — 두 섹터의 주간(r5) 승자/패자 각 3, median_r20, KOSPI/KOSDAQ 주간, LLM에 "600-word weekly wrap, English" 프롬프트. 구조는 gen_deep_dive의 render_post 패턴 재사용(공통부는 `pipeline/post_common.py`로 추출: frontmatter 직렬화·면책·마크다운 표 헬퍼).
- [ ] **Step 2: 실증** — `date`를 금요일로 가정하는 `--force` 플래그로 1회 실행, 빌드 통과 확인, 생성 파일은 실증 후 삭제(가짜 날짜 글 방지). 커밋 `feat: 주간 섹터 리뷰 생성기`

---

### Task 8: 미니 배치 — run_daily.sh + launchd

**Files:**
- Create: `pipeline/run_daily.sh`, `deploy/com.chipandcell.daily.plist`
- 미니: `~/chipandcell` 클론, `~/Library/LaunchAgents/com.chipandcell.daily.plist`

**Interfaces:**
- Consumes: Task 2·6·7 CLI
- Produces: 미니 launchd `com.chipandcell.daily` 평일 18:10 실행, 로그 `~/chipandcell/logs/daily_YYYYMMDD.log` (전체 보존)

- [ ] **Step 1: run_daily.sh**:

```bash
#!/bin/zsh
# Chip & Cell 일일 배치(미니): export → 글 생성 → commit → push
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=logs/daily_$(date +%Y%m%d).log
mkdir -p logs
{
  echo "=== $(date '+%F %T') start ==="
  git pull --rebase origin main
  python3 -m pipeline.export_data || { echo "EXPORT FAILED"; exit 1; }
  python3 -m pipeline.gen_deep_dive
  python3 -m pipeline.gen_weekly
  git add site/src/data site/src/content/posts
  if ! git diff --cached --quiet; then
    git commit -m "data: daily refresh $(date +%F)"
    git push origin main || { echo "PUSH FAILED"; exit 1; }
  else
    echo "no changes"
  fi
  echo "=== $(date '+%F %T') done ==="
} 2>&1 | tee -a "$LOG"
```
- [ ] **Step 2: plist** — Label com.chipandcell.daily, ProgramArguments=[/bin/zsh, ~/chipandcell/pipeline/run_daily.sh], StartCalendarInterval 평일 판단은 스크립트에서 하지 않고 매일 18:10 실행(주말엔 fdr 데이터 date 불변 → "no changes"로 자연 스킵), StandardOut/ErrorPath=logs/launchd.log, EnvironmentVariables에 GEMINI_API_KEY·PATH(/usr/local/bin 포함).
- [ ] **Step 3: 미니 설치** — 클론(에어 mini-remote 경유 or GitHub), `pip3 install finance-datareader google-generativeai requests` (실제 import 확인), git config author 동일 고정, GitHub push 크리덴셜 확인(미니 키체인 이슈 시 에어 허브 remote 사용 — lifelaw 선례), plist 로드.
- [ ] **Step 4: 라이브 실증** — `launchctl kickstart -k gui/$(id -u)/com.chipandcell.daily` → 로그에서 export OK→글 생성→push까지 완주 확인 → Vercel 자동 배포 → 라이브 URL에서 오늘 날짜 asof 확인. (Git 연동 미완이면 push 후 에어에서 `vercel deploy --prod` 1회로 대체하고 연동 완료를 후속 표기)
- [ ] **Step 5: 커밋** `feat: 미니 일일 배치(launchd 18:10)` + 세션 메모리 갱신

---

### Task 9: 구 블로그 동결 (kr-screener 수정)

**Files:**
- Modify(미니 `~/kr-stock-screener`): `blog_daily_deep.py`, `blog_stock_deep.py`, `blog_sector_story.py` — EN 발행 경로 차단

- [ ] **Step 1: EN 발행 호출 전수 조사** — `grep -n "republish(\|_publish_english" blog_daily_deep.py blog_stock_deep.py blog_sector_story.py blog_publisher.py` 로 세 모듈의 EN 경로 호출부 확정(republish 기본값 True 주의)
- [ ] **Step 2: 각 호출에 `publish_english=False` 명시** + 주석 `[2026-08-30] EN 블로그 동결: chipandcell.com 전환`. KR 발행 로직은 무변경.
- [ ] **Step 3: 이관 공지 글 1건 발행** — blog_publisher의 EN 블로그 API로 "Chip & Cell — we've moved" 글(새 사이트 소개+링크, 영어) 1건 게시(마지막 EN 글).
- [ ] **Step 4: 검증** — 3모듈 dry-run/임포트 확인 + grep 재확인(기본값 True republish 잔존 0) → 커밋 → **스케줄러 즉시 재시작**(launchctl unload/load, 수정 후 즉시 재시작 규칙) → 다음 거래일 EN 블로그에 자동 글 0건 확인(관찰 항목으로 보고)

---

### Task 10: 유통 준비 (도메인 후속 포함)

- [ ] **Step 1: 지금 가능한 것** — sitemap(@astrojs/sitemap 자동)·robots.txt·RSS 라이브 확인. `llms.txt`(utiltools 선례) 추가: 사이트 성격·주요 URL 목록.
- [ ] **Step 2: 도메인 연결 후(사용자 구매 대기, 차단 아님)** — GSC 등록+sitemap 제출, Bing, IndexNow 주간 launchd(lifelaw com.lifelaw.indexnow 패턴 복제, 월 09:45 미니). astro.config의 site는 이미 chipandcell.com이므로 무변경.
- [ ] **Step 3: 메모리 기록** — project_chipandcell.md 신설(+MEMORY.md 인덱스), kstock_blog_adsense·MEMORY.md에 동결 완료 반영.

---

## Self-Review 결과

- 스펙 커버리지: 정체성(T3·T4), 데이터 페이지 30개(T2·T3 — 종목27+섹터2+market1=30, index/about/methodology 별도), 심층 글(T6), 주간(T7), launchd 18:10(T8), 동결+배너(T9 — 배너는 공지 글로 구체화), 유통(T10), AdSense=계획 밖(수개월 뒤 사용자 결정) ✓
- 플레이스홀더: Task 3 Step 4의 주석 표기부는 구현 지시로 명시함 ✓
- 타입 일관성: JSON 스키마(T2)와 Astro 소비(T3), frontmatter(T5)와 생성기(T6·T7) 대조 완료 ✓
