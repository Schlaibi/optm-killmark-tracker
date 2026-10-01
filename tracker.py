"""October Killmark Challenge tracker: zKillboard -> Discord leaderboard.

Usage: python tracker.py [--dry-run] [--full]
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from killmarks import count_killmarks, count_mails, detect_tier_ups, slim_killmail
from render import render_csv, render_leaderboard, render_tier_up
from sources import fetch_new_killmails, make_session, post_or_edit, resolve_names, send_all

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
DATA = ROOT / "data"
KILLMAILS_PATH = DATA / "killmails.json"
STATE_PATH = DATA / "state.json"
CSV_PATH = DATA / "leaderboard.csv"
FULL_SCAN_EVERY = timedelta(hours=6)


def _load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _save(path, obj):
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def needs_full_scan(last_full_scan, now, end):
    """Re-page all of zKill every few hours, and every run once the event is over."""
    if last_full_scan is None or now >= _parse_time(end):
        return True
    return now - _parse_time(last_full_scan) >= FULL_SCAN_EVERY


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    dry_run = "--dry-run" in argv
    now = datetime.now(timezone.utc)
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not dry_run and not webhook:
        print("DISCORD_WEBHOOK_URL is not set")
        return 2

    config = _load(CONFIG_PATH, None)
    cache = _load(KILLMAILS_PATH, {})
    state = _load(STATE_PATH, {"message_id": None, "counts": {}, "names": {}})
    session = make_session()

    full = "--full" in argv or needs_full_scan(state.get("last_full_scan"), now, config["end"])
    try:
        new = fetch_new_killmails(session, config["corporation_id"], set(cache), full=full)
        for km in new:
            cache[str(km["killmail_id"])] = slim_killmail(km, config["corporation_id"])
        print(f"fetched {len(new)} new killmails ({len(cache)} cached){' [full scan]' if full else ''}")
        if full:
            state["last_full_scan"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    except requests.RequestException as e:
        print(f"error: {e}")
        return 1

    counts = count_killmarks(cache, config)
    names = {int(k): v for k, v in state["names"].items()}
    missing = [c for c in counts if c not in names]
    if missing:
        try:
            names.update(resolve_names(session, missing))
        except requests.RequestException as e:
            # Names are cosmetic; never let them block the leaderboard.
            print(f"warning: {e}; showing character IDs instead")

    DATA.mkdir(exist_ok=True)
    _save(KILLMAILS_PATH, cache)
    CSV_PATH.write_text(render_csv(counts, names, config["tiers"]), encoding="utf-8")

    prev = {int(k): v for k, v in state["counts"].items()}
    tier_ups = detect_tier_ups(prev, counts, config["tiers"]) if state["message_id"] else []
    leaderboard = render_leaderboard(counts, names, config, now, mails=count_mails(cache, config))

    if dry_run:
        print(leaderboard["embeds"][0]["description"])
        for char, tier in tier_ups:
            print("would announce:", render_tier_up(names.get(char, char), config["tiers"][tier - 1])["content"])
        return 0

    try:
        state["message_id"] = post_or_edit(session, webhook, leaderboard, state["message_id"])
        state["counts"] = {str(c): n for c, n in counts.items()}
        state["names"] = {str(c): n for c, n in names.items()}
        _save(STATE_PATH, state)
    except requests.RequestException as e:
        print(f"error: {e}")
        return 1
    # Announce after saving state: a failed post loses a shout-out instead of repeating them.
    send_all(session, webhook, [
        render_tier_up(names.get(char, f"Character {char}"), config["tiers"][tier - 1]) for char, tier in tier_ups
    ])
    print(f"leaderboard updated: {len(counts)} pilots, {len(tier_ups)} tier-ups")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
