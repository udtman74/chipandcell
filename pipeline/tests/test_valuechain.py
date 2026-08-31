from pipeline.tickers import TICKERS
from pipeline.valuechain import STAGES, LINKS, NOTES, stage_of


def test_every_ticker_has_exactly_one_stage():
    for code, en, _kr, sector in TICKERS:
        stages = [s["key"] for s in STAGES[sector] if code in s["codes"]]
        assert len(stages) == 1, f"{code} {en}: {stages}"


def test_stages_only_reference_known_codes():
    known = {t[0] for t in TICKERS}
    for _sector, stages in STAGES.items():
        for s in stages:
            assert set(s["codes"]) <= known


def test_links_are_sourced_and_reference_known_codes():
    known = {t[0] for t in TICKERS}
    for l in LINKS:
        assert l["from"] in known and l["to"] in known, l
        assert l["source"].startswith("http") and isinstance(l["year"], int), l
        assert l["tier"] in ("disclosure", "reported"), l
        assert l["label"].strip(), l


def test_links_have_no_self_reference_and_no_duplicate_pairs():
    seen = set()
    for l in LINKS:
        assert l["from"] != l["to"], l
        pair = (l["from"], l["to"])
        assert pair not in seen, f"duplicate edge {pair}"
        seen.add(pair)


def test_excluded_relationships_stay_excluded():
    """조사에서 반증되었거나 방향이 반대인 관계는 절대 포함되면 안 된다."""
    banned = {("042700", "005930"), ("011790", "373220"),
              ("399720", "005930"), ("005070", "373220"), ("086520", "006400")}
    assert not ({(l["from"], l["to"]) for l in LINKS} & banned)


def test_notes_reference_known_codes():
    known = {t[0] for t in TICKERS}
    assert set(NOTES) <= known


def test_stage_of():
    assert stage_of("005930") == "memory"
    assert stage_of("399720") == "design"
    assert stage_of("999999") is None
