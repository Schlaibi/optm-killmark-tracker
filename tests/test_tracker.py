from datetime import datetime, timezone

from tracker import needs_full_scan

END = "2026-11-01T00:00:00Z"


def at(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_full_scan_on_first_run():
    assert needs_full_scan(None, at("2026-10-05T12:00:00Z"), END)


def test_full_scan_every_six_hours():
    assert not needs_full_scan("2026-10-05T07:00:00Z", at("2026-10-05T12:00:00Z"), END)
    assert needs_full_scan("2026-10-05T06:00:00Z", at("2026-10-05T12:00:00Z"), END)


def test_full_scan_every_run_after_event_end():
    assert needs_full_scan("2026-11-01T00:30:00Z", at("2026-11-01T01:00:00Z"), END)
