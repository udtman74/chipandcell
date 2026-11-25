"""금요일 주간 섹터 리뷰 생성. 금요일 아니면 정상 종료(no-op).

LLM 실패는 조용히 넘기지 않는다(2026-11-15 수정): 사유를 pipeline/state/status.json에
남기고 종료 코드 1로 끝난다. 예전에는 주간 리뷰 2회(11-06, 11-13)가 표시 없이 누락됐다.
"""
import argparse
import json
import os
from datetime import datetime

from pipeline import status as runstatus
from pipeline.llm import analyze_detail
from pipeline.post_common import frontmatter, md_table, fmt_pct, DISCLAIMER, market_line

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "..", "site", "src", "data")
POSTS = os.path.join(_DIR, "..", "site", "src", "content", "posts")


def _winners_losers(stocks, sector, n=3):
    rows = [(c, s) for c, s in stocks.items() if s["sector"] == sector and s["r5"] is not None]
    rows.sort(key=lambda x: x[1]["r5"], reverse=True)
    return rows[:n], rows[-n:]


def build_prompt(stocks, sectors, market):
    parts = []
    for sec in ("semiconductor", "battery"):
        w, l = _winners_losers(stocks, sec)
        parts.append(f"{sec.capitalize()} — median 20d {fmt_pct(sectors[sec]['median_r20'])}; "
                     "week winners: " + ", ".join(f"{s['name_en']} {fmt_pct(s['r5'])}" for _, s in w) +
                     "; week laggards: " + ", ".join(f"{s['name_en']} {fmt_pct(s['r5'])}" for _, s in l))
    return f"""You are an equity research writer covering Korean stocks for a global audience.
Write a 500-650 word weekly wrap in English covering Korea's semiconductor and battery sectors.

This week's data (5-day returns, as of the Friday Seoul close):
- {parts[0]}
- {parts[1]}
- {market_line(market)}

Rules:
- Cite the specific numbers above; no generic filler that could apply to any week.
- No buy/sell recommendation, no price targets.
- Structure: the week in one paragraph → semiconductor section → battery section → short "The week ahead: what to watch" with concrete, dated catalysts only if you are confident; otherwise say the calendar is light.
- Plain markdown, section headings with ##."""


def run(force=False, today=None, data_dir=None, posts_dir=None, llm=None,
        status_path=None):
    data_dir = data_dir or DATA
    posts_dir = posts_dir or POSTS
    llm = llm or analyze_detail
    today = today or datetime.now()
    if today.weekday() != 4 and not force:
        print("weekly skip: not friday")
        runstatus.record("gen_weekly", "skipped", reason="not friday",
                         extra={"date": today.strftime("%Y-%m-%d")}, path=status_path)
        return
    date = today.strftime("%Y-%m-%d")
    out = os.path.join(posts_dir, f"{date}-weekly-review.md")
    if os.path.exists(out):
        print("weekly skip: already exists")
        runstatus.record("gen_weekly", "skipped", reason="post already exists",
                         extra={"date": date}, path=status_path)
        return
    with open(os.path.join(data_dir, "stocks.json")) as f:
        stocks = json.load(f)["stocks"]
    with open(os.path.join(data_dir, "sectors.json")) as f:
        sectors = json.load(f)["sectors"]
    with open(os.path.join(data_dir, "market.json")) as f:
        market = json.load(f)
    analysis, provider, error = llm(build_prompt(stocks, sectors, market))
    if not analysis:
        reason = error or "LLM returned no text (gemini+ollama)"
        print(f"weekly FAILED {date}: {reason}")
        runstatus.record("gen_weekly", "failed", reason=reason, extra={"date": date},
                         path=status_path)
        raise SystemExit(1)
    rows = []
    for sec in ("semiconductor", "battery"):
        w, l = _winners_losers(stocks, sec)
        rows.append([sectors[sec]["label"], fmt_pct(sectors[sec]["median_r20"]),
                     f"{w[0][1]['name_en']} {fmt_pct(w[0][1]['r5'])}",
                     f"{l[-1][1]['name_en']} {fmt_pct(l[-1][1]['r5'])}"])
    table = md_table(["Sector", "Median 20d", "Week's best (5d)", "Week's worst (5d)"], rows)
    body = "\n\n".join([
        frontmatter(f"K-Chips & Batteries Weekly — {date}", date,
                    "The week across Korea's semiconductor and battery sectors: winners, laggards and the index backdrop.",
                    sector="market", tags=["weekly"]),
        table, analysis.strip(), DISCLAIMER]) + "\n"
    os.makedirs(posts_dir, exist_ok=True)
    with open(out, "w") as f:
        f.write(body)
    print(f"weekly OK ({provider}) -> {os.path.basename(out)}")
    runstatus.record("gen_weekly", "ok", extra={"date": date, "provider": provider,
                                                "post": os.path.basename(out)},
                     path=status_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="금요일 아니어도 생성(실증용)")
    run(force=ap.parse_args().force)
