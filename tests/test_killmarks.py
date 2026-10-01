import copy
import json
from pathlib import Path

import pytest

from killmarks import count_killmarks, current_tier, detect_tier_ups, slim_killmail

CORP = 98707560
CONFIG = json.loads((Path(__file__).parent.parent / "config.json").read_text(encoding="utf-8"))
TIERS = CONFIG["tiers"]

_next_id = [1000]


def make_km(time="2026-10-05T12:00:00Z", victim_ship=587, victim_corp=1, victim_alli=2,
            npc=False, attackers=((10, CORP),)):
    _next_id[0] += 1
    victim = {"ship_type_id": victim_ship, "corporation_id": victim_corp}
    if victim_alli is not None:
        victim["alliance_id"] = victim_alli
    atts = []
    for char, corp in attackers:
        a = {"corporation_id": corp, "ship_type_id": 11978}
        if char is not None:
            a["character_id"] = char
        atts.append(a)
    return {
        "killmail_id": _next_id[0],
        "killmail_time": time,
        "victim": victim,
        "attackers": atts,
        "zkb": {"npc": npc, "hash": "abc"},
    }


def slims(*kms):
    return {str(km["killmail_id"]): slim_killmail(km, CORP) for km in kms}


def config(**overrides):
    c = copy.deepcopy(CONFIG)
    c.update(overrides)
    return c


def test_slim_keeps_only_corp_chars_deduped():
    km = make_km(attackers=[(10, CORP), (10, CORP), (11, 555), (None, CORP)])
    assert slim_killmail(km, CORP)["chars"] == [10]


def test_counts_each_corp_char_once_per_mail():
    s = slims(make_km(attackers=[(10, CORP), (20, CORP)]), make_km(attackers=[(10, CORP)]))
    assert count_killmarks(s, config()) == {10: 2, 20: 1}


def test_pod_kills_excluded():
    s = slims(make_km(victim_ship=670), make_km(victim_ship=33328))
    assert count_killmarks(s, config()) == {}


def test_npc_excluded():
    assert count_killmarks(slims(make_km(npc=True)), config()) == {}


def test_blue_alliance_excluded():
    assert count_killmarks(slims(make_km(victim_alli=99003581)), config()) == {}
    assert count_killmarks(slims(make_km(victim_alli=1354830081)), config()) == {10: 1}


def test_blue_corporation_excluded():
    s = slims(make_km(victim_corp=777, victim_alli=None))
    assert count_killmarks(s, config(blue_corporations=[777])) == {}


def test_victim_without_alliance_counts():
    assert count_killmarks(slims(make_km(victim_alli=None)), config()) == {10: 1}


@pytest.mark.parametrize("time,counted", [
    ("2026-09-30T23:59:59Z", False),
    ("2026-10-01T00:00:00Z", True),
    ("2026-10-31T23:59:59Z", True),
    ("2026-11-01T00:00:00Z", False),
])
def test_window_edges(time, counted):
    result = count_killmarks(slims(make_km(time=time)), config())
    assert result == ({10: 1} if counted else {})


def test_disqualified_removed_even_with_adjustment():
    s = slims(make_km(attackers=[(10, CORP), (20, CORP)]))
    result = count_killmarks(s, config(disqualified=[10], adjustments={"10": 5}))
    assert result == {20: 1}


def test_adjustments_apply_and_drop_nonpositive():
    s = slims(make_km(attackers=[(20, CORP), (30, CORP)]))
    result = count_killmarks(s, config(adjustments={"20": 3, "30": -1}))
    assert result == {20: 4}


@pytest.mark.parametrize("marks,tier", [(0, 0), (199, 0), (200, 1), (999, 2), (1000, 3), (5000, 3)])
def test_current_tier(marks, tier):
    assert current_tier(marks, TIERS) == tier


def test_tier_up_reports_highest_only():
    assert detect_tier_ups({1: 150}, {1: 520, 2: 100}, TIERS) == [(1, 2)]


def test_tier_up_new_char():
    assert detect_tier_ups({}, {3: 200}, TIERS) == [(3, 1)]
