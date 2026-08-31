from pipeline.record_ledger import snapshot, append, attach_note

M = {"close": 100.0, "pos52": 50.0, "ma20": 80.0, "ma60": 125.0, "r20": 12.345}
STORE = {"flows": {"005930": {f"2026-08-2{d}": {"f": 2, "i": -1, "p": -1} for d in range(1, 7)}}}


def test_snapshot_fields():
    r = snapshot("005930", M, STORE, "2026-08-26", backfilled=True)
    assert r["code"] == "005930" and r["date"] == "2026-08-26"
    assert r["vs_ma20"] == 25.0 and r["vs_ma60"] == -20.0
    assert r["flow5_f"] == 10 and r["flow5_i"] == -5
    assert r["backfilled"] is True
    assert r["note"] is None and r["verified"] is None


def test_snapshot_flow_none_when_insufficient_history():
    r = snapshot("000660", M, STORE, "2026-08-26", backfilled=False)
    assert r["flow5_f"] is None and r["flow5_i"] is None


def test_append_is_idempotent():
    led = {"updated": "", "records": []}
    r = snapshot("005930", M, STORE, "2026-08-26", backfilled=False)
    assert append(led, r) is True
    assert append(led, dict(r)) is False
    assert len(led["records"]) == 1


def test_attach_note_sets_note_and_post():
    led = {"updated": "", "records": [snapshot("005930", M, STORE, "2026-08-26", False)]}
    assert attach_note(led, "005930", "2026-08-26", "Foreign selling persisted.",
                       "2026-08-26-samsung") is True
    assert led["records"][0]["note_post"] == "2026-08-26-samsung"
    assert attach_note(led, "005930", "2026-01-01", "x", "y") is False
