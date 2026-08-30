"""일 1건 심층 글 생성: 이벤트(|pct|>=5%) 우선, 평시 로테이션 큐."""
import json
import os
import re
from datetime import datetime, timedelta

from pipeline.tickers import TICKERS
from pipeline.llm import analyze
from pipeline.post_common import frontmatter, md_table, fmt_pct, fmt_won, DISCLAIMER

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "..", "site", "src", "data")
POSTS = os.path.join(_DIR, "..", "site", "src", "content", "posts")
STATE = os.path.join(_DIR, "state", "rotation.json")

EVENT_PCT = 5.0
COOLDOWN_DAYS = 7


def pick_target(stocks, state, today):
    """이벤트 종목(쿨다운 밖, |pct| 최대) 우선, 없으면 큐 회전. state를 변경한다."""
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=COOLDOWN_DAYS)).strftime("%Y-%m-%d")
    last = state.get("last_events", {})
    # 미기록 종목은 last.get(c, "")="" < cutoff 이므로 항상 통과
    events = [c for c, s in stocks.items()
              if abs(s.get("pct") or 0) >= EVENT_PCT and last.get(c, "") < cutoff]
    if events:
        code = max(events, key=lambda c: abs(stocks[c]["pct"]))
        state.setdefault("last_events", {})[code] = today
        if code in state.get("queue", []):
            state["queue"].remove(code)
            state["queue"].append(code)
        return code
    queue = state.setdefault("queue", [t[0] for t in TICKERS])
    code = queue.pop(0)
    queue.append(code)
    return code


def _load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {"queue": [t[0] for t in TICKERS], "last_events": {}}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def build_prompt(code, s, sector_ctx, market):
    flow = s.get("flow") or {}
    flow_txt = (f"Foreign net {flow.get('foreign_net', 'n/a')}, institutional net "
                f"{flow.get('inst_net', 'n/a')} shares.") if flow else "Flow data unavailable today."
    return f"""You are an equity research writer covering Korean stocks for a global audience.
Write a 500-700 word analyst-style note in English about {s['name_en']} (KRX {code}), a Korean {s['sector']} stock.

Today's data (as of {s['date']}, KST close):
- Close {fmt_won(s['close'])}, day change {fmt_pct(s['pct'])}
- Returns: 5-day {fmt_pct(s['r5'])}, 20-day {fmt_pct(s['r20'])}, 60-day {fmt_pct(s['r60'])}
- 52-week range {fmt_won(s['lo52'])}–{fmt_won(s['hi52'])}, currently at {s['pos52']}% of the range
- MA20 {fmt_won(s['ma20'])}, MA60 {fmt_won(s['ma60'])}
- {flow_txt}
- Sector context: covered Korean {s['sector']} names median 20-day return {fmt_pct(sector_ctx['median_r20'])}
- Market: KOSPI {fmt_pct(market['kospi']['pct'])} today, KOSDAQ {fmt_pct(market['kosdaq']['pct'])}

Rules:
- Cite the specific numbers above; every claim must be tied to a number or a well-known, dated fact about the company.
- No generic filler that could apply to any stock. No buy/sell recommendation, no price target.
- Structure: what the stock did and where it stands (vs its own range, MAs and sector) → what could explain it (company-specific drivers you are confident about) → close with a short "Risks and caveats" section.
- Plain markdown, section headings with ##. Do not repeat the data table verbatim; interpret it."""


def render_post(code, s, analysis, today):
    title = f"{s['name_en']} ({code}): Where It Stands — {today} Deep Dive"
    desc = (f"Data-driven look at {s['name_en']}: {fmt_pct(s['pct'])} on the day, "
            f"20-day {fmt_pct(s['r20'])}, {s['pos52']}% of its 52-week range.")
    table = md_table(
        ["Metric", "Value"],
        [["Close", fmt_won(s["close"])], ["Day", fmt_pct(s["pct"])],
         ["5d / 20d / 60d", f"{fmt_pct(s['r5'])} / {fmt_pct(s['r20'])} / {fmt_pct(s['r60'])}"],
         ["52w position", f"{s['pos52']}% ({fmt_won(s['lo52'])}–{fmt_won(s['hi52'])})"],
         ["MA20 / MA60", f"{fmt_won(s['ma20'])} / {fmt_won(s['ma60'])}"]])
    return "\n\n".join([
        frontmatter(title, today, desc, ticker=code, sector=s["sector"],
                    tags=["deep-dive", s["sector"]]),
        f"*As of {s['date']} (Seoul close). Live numbers on the "
        f"[{s['name_en']} data page](/stocks/{code}/).*",
        table, analysis.strip(), DISCLAIMER]) + "\n"


def run():
    with open(os.path.join(DATA, "stocks.json")) as f:
        stocks_doc = json.load(f)
    with open(os.path.join(DATA, "sectors.json")) as f:
        sectors = json.load(f)["sectors"]
    with open(os.path.join(DATA, "market.json")) as f:
        market = json.load(f)
    stocks = stocks_doc["stocks"]
    today = datetime.now().strftime("%Y-%m-%d")
    state = _load_state()
    code = pick_target(stocks, state, today)
    s = stocks[code]
    out = os.path.join(POSTS, f"{today}-{_slug(s['name_en'])}.md")
    if os.path.exists(out):
        print(f"deep dive skip: {out} already exists")
        return
    analysis = analyze(build_prompt(code, s, sectors[s["sector"]], market))
    if not analysis:
        print("deep dive skip: LLM unavailable (gemini+ollama failed)")
        return
    os.makedirs(POSTS, exist_ok=True)
    with open(out, "w") as f:
        f.write(render_post(code, s, analysis, today))
    _save_state(state)
    print(f"deep dive OK {code} {s['name_en']} -> {os.path.basename(out)}")


if __name__ == "__main__":
    run()
