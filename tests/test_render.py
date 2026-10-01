import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from render import progress_line, render_csv, render_leaderboard, render_tier_up

CONFIG = json.loads((Path(__file__).parent.parent / "config.json").read_text(encoding="utf-8"))
TIERS = CONFIG["tiers"]
NOW = datetime(2026, 10, 5, 18, 30, tzinfo=timezone.utc)


def test_progress_line_mid_tier():
    line = progress_line(3, "Pilot", 612, TIERS)
    assert line.startswith("`#3` **Pilot** — 612 ")
    assert "🥈" in line and "388 to 🥇" in line
    assert line.count("▰") == 2 and line.count("▱") == 8


def test_progress_line_below_first_tier():
    line = progress_line(9, "Pilot", 50, TIERS)
    assert "150 to 🥉" in line
    assert line.count("▰") == 2
    before_dot = line.split("·")[0]
    assert not any(t["emoji"] in before_dot for t in TIERS)


def test_progress_line_max():
    line = progress_line(1, "Pilot", 1204, TIERS)
    assert "1,204" in line and line.endswith("🥇 MAX")
    assert line.count("▰") == 10


def test_leaderboard_sorted_and_summary():
    payload = render_leaderboard({3: 10, 1: 600, 2: 250}, {1: "Alpha", 2: "Bravo", 3: "Charlie"}, CONFIG, NOW)
    embed = payload["embeds"][0]
    desc = embed["description"]
    assert desc.index("Alpha") < desc.index("Bravo") < desc.index("Charlie")
    summary = desc.splitlines()[0]
    assert "**3** pilots" in summary and "🥉 2" in summary and "🥈 1" in summary and "🥇 0" in summary
    assert embed["title"] == "☠️ October Killmark Challenge"
    assert embed["footer"]["text"].startswith("Updated 2026-10-05 18:30 UTC")


def test_leaderboard_trims_to_4096():
    counts = {i: 1000 - i for i in range(300)}
    names = {i: f"{'X' * 36}{i:04d}" for i in range(300)}
    config = dict(CONFIG, leaderboard_size=300)
    desc = render_leaderboard(counts, names, config, NOW)["embeds"][0]["description"]
    assert len(desc) <= 4096
    assert desc.endswith("full list in leaderboard.csv")


def test_leaderboard_empty():
    desc = render_leaderboard({}, {}, CONFIG, NOW)["embeds"][0]["description"]
    assert desc == "No killmarks yet — undock! o7"


def test_unknown_name_falls_back():
    desc = render_leaderboard({42: 5}, {}, CONFIG, NOW)["embeds"][0]["description"]
    assert "Character 42" in desc


def test_no_mentions_parsed():
    assert render_leaderboard({1: 5}, {1: "@everyone"}, CONFIG, NOW)["allowed_mentions"] == {"parse": []}
    assert render_tier_up("@everyone", TIERS[0])["allowed_mentions"] == {"parse": []}


def test_tier_up_text():
    assert render_tier_up("Pilot", TIERS[0])["content"] == (
        "🥉 **Pilot** just hit **200 killmarks**! (1 Marauder of choice)"
    )


def test_csv_rows():
    text = render_csv({7: 5, 8: 250}, {7: "Seven", 8: "Eight"}, TIERS)
    rows = list(csv.reader(io.StringIO(text)))
    assert len(rows) == 3
    assert rows[0] == ["rank", "character", "character_id", "killmarks", "tier", "zkill"]
    assert rows[1] == ["1", "Eight", "8", "250", "1", "https://zkillboard.com/character/8/"]
