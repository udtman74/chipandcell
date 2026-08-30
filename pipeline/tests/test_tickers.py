import re
from pipeline.tickers import TICKERS, SEMI, BATT


def test_counts():
    assert len(SEMI) == 15 and len(BATT) == 12 and len(TICKERS) == 27


def test_codes_unique_and_valid():
    codes = [t[0] for t in TICKERS]
    assert len(set(codes)) == 27
    assert all(re.fullmatch(r"\d{6}", c) for c in codes)
