"""Pure killmark counting rules. No I/O."""
from datetime import datetime


def _parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def slim_killmail(km, corp_id):
    """Reduce a full zKill/ESI killmail to what the counting rules need."""
    victim = km["victim"]
    chars = {
        a["character_id"]
        for a in km.get("attackers", [])
        if a.get("corporation_id") == corp_id and a.get("character_id")
    }
    return {
        "t": km["killmail_time"],
        "ship": victim.get("ship_type_id"),
        "vcorp": victim.get("corporation_id"),
        "valli": victim.get("alliance_id"),
        "npc": bool(km.get("zkb", {}).get("npc", False)),
        "chars": sorted(chars),
    }


def _counts(slim, config, start, end):
    if not start <= _parse_time(slim["t"]) < end:
        return False
    if slim["ship"] in config["pod_type_ids"] or slim["npc"]:
        return False
    if slim["valli"] in config["blue_alliances"]:
        return False
    if slim["vcorp"] in config["blue_corporations"]:
        return False
    return True


def _counted(slims, config):
    start, end = _parse_time(config["start"]), _parse_time(config["end"])
    return [s for s in slims.values() if s["chars"] and _counts(s, config, start, end)]


def count_mails(slims, config):
    """Number of killmails that earn killmarks."""
    return len(_counted(slims, config))


def count_killmarks(slims, config):
    """Return {character_id: killmarks} after rules, disqualifications and adjustments."""
    counts = {}
    for slim in _counted(slims, config):
        for char in slim["chars"]:
            counts[char] = counts.get(char, 0) + 1

    for char_id, delta in config["adjustments"].items():
        counts[int(char_id)] = counts.get(int(char_id), 0) + int(delta)
    for char_id in config["disqualified"]:
        counts.pop(int(char_id), None)
    return {c: n for c, n in counts.items() if n > 0}


def current_tier(marks, tiers):
    """Number of tiers reached (0 = none)."""
    return sum(1 for t in tiers if marks >= t["marks"])


def detect_tier_ups(prev, now, tiers):
    """[(character_id, tier_reached)] for characters whose tier rose, highest tier first."""
    ups = []
    for char, marks in now.items():
        new = current_tier(marks, tiers)
        if new > current_tier(prev.get(char, 0), tiers):
            ups.append((char, new))
    return sorted(ups, key=lambda u: (-u[1], u[0]))
