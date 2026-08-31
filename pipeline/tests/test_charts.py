import pandas as pd

from pipeline.charts import candle_svg, flow_svg, scatter_svg


def _ohlc(n):
    idx = pd.bdate_range("2026-01-01", periods=n)
    return pd.DataFrame({"Open": [100.0] * n, "High": [110.0] * n,
                         "Low": [90.0] * n, "Close": [105.0] * n}, index=idx)


def test_candle_returns_svg_and_uses_css_vars():
    out = candle_svg(_ohlc(60), title="Test")
    assert out.startswith("<svg") and out.rstrip().endswith("</svg>")
    assert 'style="fill:var(--up)' in out or 'style="stroke:var(--up)' in out
    assert 'fill="var(' not in out          # 표현 속성에 var() 쓰면 브라우저가 해석 못 함
    assert 'stroke="var(' not in out


def test_candle_empty_when_too_short():
    assert candle_svg(_ohlc(5)) == ""


def test_flow_svg_empty_when_too_short():
    assert flow_svg(["2026-08-03"], [1], [2]) == ""


def test_flow_svg_renders_two_series():
    dates = [f"2026-08-{d:02d}" for d in range(3, 11)]
    out = flow_svg(dates, [1] * 8, [-1] * 8)
    assert out.count("<polyline") == 2


def test_scatter_empty_when_too_few_points():
    assert scatter_svg([("A", 1.0, 2.0)]) == ""


def test_scatter_renders_all_points():
    pts = [("A", 1.0, 2.0), ("B", -3.0, 4.0), ("C", 5.0, -1.0)]
    assert scatter_svg(pts).count("<circle") == 3
