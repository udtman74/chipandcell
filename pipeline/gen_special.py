"""지수(KOSPI/KOSDAQ)·섹터 심층 리포트 생성 — 런칭 특집 및 수시 사용.

usage: python3 -m pipeline.gen_special market kospi|kosdaq
       python3 -m pipeline.gen_special sector semiconductor|battery
"""
import argparse
import json
import os
from datetime import datetime

import FinanceDataReader as fdr

from pipeline.metrics import compute
from pipeline.llm import analyze
from pipeline.post_common import frontmatter, md_table, fmt_pct, fmt_won, DISCLAIMER

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "..", "site", "src", "data")
POSTS = os.path.join(_DIR, "..", "site", "src", "content", "posts")

INDICES = {
    "kospi": ("KOSPI", ("KS11", "^KS11")),
    "kosdaq": ("KOSDAQ", ("KQ11", "^KQ11")),
}


def _load():
    with open(os.path.join(DATA, "stocks.json")) as f:
        stocks = json.load(f)["stocks"]
    with open(os.path.join(DATA, "sectors.json")) as f:
        sectors = json.load(f)["sectors"]
    return stocks, sectors


def _fetch_index(syms):
    for sym in syms:
        df = fdr.DataReader(sym)
        if len(df) and "Close" in df.columns:
            return compute(df)
    raise SystemExit(f"index fetch failed: {syms}")


def _write(out, body):
    os.makedirs(POSTS, exist_ok=True)
    with open(out, "w") as f:
        f.write(body)
    print(f"special OK -> {os.path.basename(out)}")


def market_report(key):
    name, syms = INDICES[key]
    m = _fetch_index(syms)
    _, sectors = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    out = os.path.join(POSTS, f"{today}-{key}-deep-dive.md")
    if os.path.exists(out):
        print(f"skip: {out} exists")
        return
    lvl = f"{m['close']:,.2f}"
    prompt = f"""You are an equity research writer covering the Korean market for a global audience.
Write a 500-700 word analyst-style note in English on the {name} index.

Data (as of {m['date']}, KST close):
- Level {lvl}, day change {fmt_pct(m['pct'])}
- Returns: 5-day {fmt_pct(m['r5'])}, 20-day {fmt_pct(m['r20'])}, 60-day {fmt_pct(m['r60'])}
- 52-week range {m['lo52']:,.2f}–{m['hi52']:,.2f}, currently at {m['pos52']}% of the range
- MA20 {m['ma20']:,.2f}, MA60 {m['ma60']:,.2f}
- Sector pulse from our coverage: Korean semiconductor names median 20-day return {fmt_pct(sectors['semiconductor']['median_r20'])}; battery names median {fmt_pct(sectors['battery']['median_r20'])}

Rules:
- Cite the specific numbers above; every claim must be tied to a number or a well-known, dated market fact.
- No generic filler that could apply to any index at any time. No forecasts of specific levels, no buy/sell language.
- Structure: where the index stands (vs its 52-week range and moving averages) → what the momentum readings say across the three horizons → how the semiconductor/battery pulse relates to the tape → "Risks and caveats".
- Plain markdown, ## section headings. Interpret the data; do not restate it as a list."""
    analysis = analyze(prompt)
    if not analysis:
        print("skip: LLM unavailable")
        return
    table = md_table(
        ["Metric", "Value"],
        [["Level", lvl], ["Day", fmt_pct(m["pct"])],
         ["5d / 20d / 60d", f"{fmt_pct(m['r5'])} / {fmt_pct(m['r20'])} / {fmt_pct(m['r60'])}"],
         ["52w position", f"{m['pos52']}% ({m['lo52']:,.2f}–{m['hi52']:,.2f})"],
         ["MA20 / MA60", f"{m['ma20']:,.2f} / {m['ma60']:,.2f}"]])
    body = "\n\n".join([
        frontmatter(f"{name} Deep Dive: Where the Index Stands — {today}", today,
                    f"Data-driven look at the {name}: {fmt_pct(m['pct'])} on the day, "
                    f"20-day {fmt_pct(m['r20'])}, {m['pos52']}% of its 52-week range.",
                    sector="market", tags=["deep-dive", "index", key]),
        f"*As of {m['date']} (Seoul close). Live numbers on the [market page](/market/).*",
        table, analysis.strip(), DISCLAIMER]) + "\n"
    _write(out, body)


def sector_report(sector):
    stocks, sectors = _load()
    sec = sectors[sector]
    today = datetime.now().strftime("%Y-%m-%d")
    out = os.path.join(POSTS, f"{today}-{sector}-sector-deep-dive.md")
    if os.path.exists(out):
        print(f"skip: {out} exists")
        return
    rows = sorted(((c, s) for c, s in stocks.items() if s["sector"] == sector),
                  key=lambda x: (x[1]["r20"] is None, -(x[1]["r20"] or 0)))
    lines = "\n".join(
        f"- {s['name_en']} ({c}): close {fmt_won(s['close'])}, day {fmt_pct(s['pct'])}, "
        f"5d {fmt_pct(s['r5'])}, 20d {fmt_pct(s['r20'])}, 52w position {s['pos52']}%"
        for c, s in rows)
    label = sec["label"]
    prompt = f"""You are an equity research writer covering Korean stocks for a global audience.
Write a 600-800 word analyst-style sector note in English on the Korean {label.lower()} sector,
based on our fixed coverage universe of {len(rows)} KOSPI/KOSDAQ names.

Data (as of the latest Seoul close):
{lines}
- Sector median 20-day return: {fmt_pct(sec['median_r20'])}; last session {sec['advancers']} advancing / {sec['decliners']} declining.

Rules:
- Cite the specific numbers above; name specific companies when making claims.
- Only include company- or industry-specific drivers you are confident about (well-known, dated facts); otherwise stay with the data.
- No generic filler, no buy/sell language, no price targets.
- Structure: the state of the sector in one paragraph → leaders and what distinguishes them → laggards and stress points → dispersion/rotation observations (who is at 52-week extremes) → "Risks and caveats".
- Plain markdown, ## section headings. Interpret the data; do not repeat the list verbatim."""
    analysis = analyze(prompt)
    if not analysis:
        print("skip: LLM unavailable")
        return
    table = md_table(
        ["Name", "Close", "Day", "20d", "52w pos"],
        [[f"[{s['name_en']}](/stocks/{c}/)", fmt_won(s["close"]), fmt_pct(s["pct"]),
          fmt_pct(s["r20"]), f"{s['pos52']}%"] for c, s in rows])
    body = "\n\n".join([
        frontmatter(f"Korean {label} Sector Deep Dive — {today}", today,
                    f"All {len(rows)} covered Korean {label.lower()} names ranked and interpreted: "
                    f"median 20-day {fmt_pct(sec['median_r20'])}, leaders, laggards and dispersion.",
                    sector=sector, tags=["deep-dive", "sector", sector]),
        f"*As of the latest Seoul close. Live table on the [{label.lower()} page](/{sector}/).*",
        table, analysis.strip(), DISCLAIMER]) + "\n"
    _write(out, body)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["market", "sector"])
    ap.add_argument("key")
    a = ap.parse_args()
    if a.kind == "market":
        market_report(a.key)
    else:
        sector_report(a.key)
