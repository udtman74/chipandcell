"""금요일 주간 섹터 리뷰 생성. 금요일 아니면 정상 종료(no-op)."""
import argparse
import json
import os
from datetime import datetime

from pipeline.llm import analyze
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


def run(force=False):
    today = datetime.now()
    if today.weekday() != 4 and not force:
        print("weekly skip: not friday")
        return
    date = today.strftime("%Y-%m-%d")
    out = os.path.join(POSTS, f"{date}-weekly-review.md")
    if os.path.exists(out):
        print("weekly skip: already exists")
        return
    with open(os.path.join(DATA, "stocks.json")) as f:
        stocks = json.load(f)["stocks"]
    with open(os.path.join(DATA, "sectors.json")) as f:
        sectors = json.load(f)["sectors"]
    with open(os.path.join(DATA, "market.json")) as f:
        market = json.load(f)
    analysis = analyze(build_prompt(stocks, sectors, market))
    if not analysis:
        print("weekly skip: LLM unavailable")
        return
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
    with open(out, "w") as f:
        f.write(body)
    print(f"weekly OK -> {os.path.basename(out)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="금요일 아니어도 생성(실증용)")
    run(force=ap.parse_args().force)
