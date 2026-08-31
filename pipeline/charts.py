"""빌드 시점 인라인 SVG 차트. 외부 라이브러리·자바스크립트 없음.

색상은 표현 속성이 아니라 style 인라인으로 CSS 변수를 참조한다
(fill="var(--up)"는 브라우저가 해석하지 않는다 — 차트가 검게 나오거나 사라진다).
인라인 삽입이므로 페이지의 라이트/다크 토큰을 그대로 상속한다.
"""
import json
import os

import FinanceDataReader as fdr

from pipeline.tickers import TICKERS, SECTOR_LABELS
from pipeline.flow_history import load as load_flows

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "..", "site", "src", "data")
OUT = os.path.join(DATA, "charts")
W, H, PAD = 720, 240, 40

_SVG = ('<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="{alt}" style="width:100%;height:auto">{body}</svg>')


def _txt(x, y, t, anchor=None, size=11, var="--muted"):
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" style="fill:var({var})"{a}>{t}</text>'


def candle_svg(df, title=""):
    """일봉 캔들. df=OHLC(오름차순). 10봉 미만이면 ""."""
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 10:
        return ""
    lo, hi = float(df["Low"].min()), float(df["High"].max())
    span = (hi - lo) or 1

    def y(p):
        return round(PAD + (hi - p) / span * (H - 2 * PAD), 1)

    n = len(df)
    step = (W - 2 * PAD) / n
    cw = max(2, round(step * 0.6, 1))
    parts = []
    for i, (_, r) in enumerate(df.iterrows()):
        x = round(PAD + i * step + step / 2, 1)
        o, c, h_, l_ = float(r["Open"]), float(r["Close"]), float(r["High"]), float(r["Low"])
        var = "var(--up)" if c >= o else "var(--down)"
        parts.append(f'<line x1="{x}" y1="{y(h_)}" x2="{x}" y2="{y(l_)}" '
                     f'style="stroke:{var}" stroke-width="1"/>')
        top, bot = y(max(o, c)), y(min(o, c))
        parts.append(f'<rect x="{round(x - cw / 2, 1)}" y="{top}" width="{cw}" '
                     f'height="{max(1, round(bot - top, 1))}" style="fill:{var}"/>')
    d0 = df.index[0].strftime("%Y-%m-%d")
    d1 = df.index[-1].strftime("%Y-%m-%d")
    axis = (_txt(PAD, H - 10, d0) + _txt(W - PAD, H - 10, d1, "end")
            + _txt(W - PAD, y(hi) + 10, f"{hi:,.0f}", "end")
            + _txt(W - PAD, y(lo), f"{lo:,.0f}", "end"))
    cap = _txt(PAD, PAD - 16, title, size=12) if title else ""
    return _SVG.format(w=W, h=H, alt=title or "Candlestick chart",
                       body=cap + axis + "".join(parts))


def flow_svg(dates, f_vals, i_vals, title=""):
    """외국인·기관 누적 순매수 2개 라인. 5일 미만이면 ""."""
    if len(dates) < 5:
        return ""

    def _cum(vals):
        out, acc = [], 0
        for v in vals:
            acc += v
            out.append(acc)
        return out

    fc, ic = _cum(f_vals), _cum(i_vals)
    lo = min(min(fc), min(ic), 0)
    hi = max(max(fc), max(ic), 0)
    span = (hi - lo) or 1
    n = len(dates)
    step = (W - 2 * PAD) / max(1, n - 1)

    def y(v):
        return round(PAD + (hi - v) / span * (H - 2 * PAD), 1)

    def line(series, var):
        pts = " ".join(f"{round(PAD + i * step, 1)},{y(v)}" for i, v in enumerate(series))
        return f'<polyline points="{pts}" fill="none" style="stroke:{var}" stroke-width="2"/>'

    zero = (f'<line x1="{PAD}" y1="{y(0)}" x2="{W - PAD}" y2="{y(0)}" '
            f'style="stroke:var(--line)" stroke-width="1" stroke-dasharray="4,3"/>')
    legend = (_txt(PAD, PAD - 16, "Cumulative net buying —", size=12)
              + _txt(PAD + 172, PAD - 16, "Foreign", size=12, var="--series-a")
              + _txt(PAD + 228, PAD - 16, "Institutions", size=12, var="--series-b"))
    axis = _txt(PAD, H - 10, dates[0]) + _txt(W - PAD, H - 10, dates[-1], "end")
    return _SVG.format(w=W, h=H, alt=title or "Cumulative investor flows",
                       body=legend + axis + zero
                            + line(fc, "var(--series-a)") + line(ic, "var(--series-b)"))


def scatter_svg(points, title=""):
    """points=[(label, x, y)] 산점도. 3점 미만이면 ""."""
    if len(points) < 3:
        return ""
    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    x0, x1 = min(xs + [0]), max(xs + [0])
    y0, y1 = min(ys + [0]), max(ys + [0])
    xs_span = (x1 - x0) or 1
    ys_span = (y1 - y0) or 1

    def px(v):
        return round(PAD + (v - x0) / xs_span * (W - 2 * PAD), 1)

    def py(v):
        return round(PAD + (y1 - v) / ys_span * (H - 2 * PAD), 1)

    body = [
        f'<line x1="{PAD}" y1="{py(0)}" x2="{W - PAD}" y2="{py(0)}" '
        f'style="stroke:var(--line)" stroke-width="1"/>',
        f'<line x1="{px(0)}" y1="{PAD}" x2="{px(0)}" y2="{H - PAD}" '
        f'style="stroke:var(--line)" stroke-width="1"/>',
        _txt(PAD, PAD - 16, title or "20-day vs 60-day return (%)", size=12),
        _txt(W - PAD, H - 10, "60-day return →", "end"),
    ]
    for label, x, y in points:
        body.append(f'<circle cx="{px(x)}" cy="{py(y)}" r="4" style="fill:var(--series-a)"/>')
        body.append(_txt(px(x) + 6, py(y) - 5, label, size=10))
    return _SVG.format(w=W, h=H, alt=title or "Sector rotation scatter", body="".join(body))


def _write(name, svg):
    if not svg:
        return 0
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(svg)
    return 1


def build_all():
    with open(os.path.join(DATA, "stocks.json")) as f:
        doc = json.load(f)
    stocks, asof = doc["stocks"], doc["asof"]
    flows = load_flows()
    made = 0
    for code, en, _kr, _sec in TICKERS:
        s = stocks.get(code)
        if not s or s["date"] != asof:      # 스테일 가드: 최신이 아니면 그리지 않는다
            continue
        try:
            df = fdr.DataReader(code).tail(60)
        except Exception as e:
            print(f"  ⚠️ {code} chart skipped: {e!r}")
            continue
        made += _write(f"{code}-candle.svg", candle_svg(df, f"{en} — last 60 sessions"))
        per = flows.get("flows", {}).get(code, {})
        days = sorted(per)[-30:]
        made += _write(f"{code}-flow.svg",
                       flow_svg(days, [per[d]["f"] for d in days], [per[d]["i"] for d in days]))
    for sector, label in SECTOR_LABELS.items():
        pts = [(s["name_en"], s["r60"], s["r20"]) for _c, s in stocks.items()
               if s["sector"] == sector and s["r20"] is not None and s["r60"] is not None]
        made += _write(f"{sector}-scatter.svg",
                       scatter_svg(pts, f"{label}: 20-day vs 60-day return (%)"))
    print(f"charts OK {made} files")


if __name__ == "__main__":
    build_all()
