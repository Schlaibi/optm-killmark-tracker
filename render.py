"""Pure rendering of the Discord leaderboard, tier-up posts and CSV export. No I/O."""
import csv
import io

from killmarks import current_tier

TITLE = "☠️ October Killmark Challenge"
COLOR = 0xB22222
BAR_CELLS = 10
MAX_DESCRIPTION = 4096
NO_MENTIONS = {"parse": []}


def _name(char_id, names):
    return names.get(char_id) or f"Character {char_id}"


def _ranked(counts, names):
    return sorted(counts.items(), key=lambda kv: (-kv[1], _name(kv[0], names).lower()))


def progress_line(rank, name, marks, tiers):
    tier = current_tier(marks, tiers)
    head = f"`#{rank}` **{name}** — {marks:,} "
    if tier == len(tiers):
        return head + "▰" * BAR_CELLS + f" {tiers[-1]['emoji']} MAX"
    floor = tiers[tier - 1]["marks"] if tier else 0
    target = tiers[tier]
    filled = BAR_CELLS * (marks - floor) // (target["marks"] - floor)
    bar = "▰" * filled + "▱" * (BAR_CELLS - filled)
    badge = f" {tiers[tier - 1]['emoji']}" if tier else ""
    return f"{head}{bar}{badge} · {target['marks'] - marks:,} to {target['emoji']}"


def render_leaderboard(counts, names, config, now, mails=0):
    tiers = config["tiers"]
    if not counts:
        description = "No killmarks yet — undock! o7"
    else:
        reached = [sum(1 for m in counts.values() if m >= t["marks"]) for t in tiers]
        summary = f"**{len(counts)}** pilots · **{mails:,}** mails · " + " · ".join(
            f"{t['emoji']} {n}" for t, n in zip(tiers, reached)
        )
        ranked = _ranked(counts, names)
        lines = [
            progress_line(i, _name(c, names), m, tiers)
            for i, (c, m) in enumerate(ranked[: config["leaderboard_size"]], start=1)
        ]
        description = _fit(summary, lines, len(ranked))
    return {
        "embeds": [{
            "title": TITLE,
            "description": description,
            "color": COLOR,
            "footer": {"text": f"Updated {now:%Y-%m-%d %H:%M} UTC · pods & blues excluded · leadership has final say"},
        }],
        "allowed_mentions": NO_MENTIONS,
    }


def _fit(summary, lines, total):
    """Join summary + lines, dropping lines from the bottom until it fits Discord's limit."""
    shown = len(lines)
    while True:
        text = summary + "\n\n" + "\n".join(lines[:shown])
        hidden = total - shown
        if hidden:
            text += f"\n+{hidden} more — full list in leaderboard.csv"
        if len(text) <= MAX_DESCRIPTION:
            return text
        shown -= 1


def render_tier_up(name, tier):
    return {
        "content": f"{tier['emoji']} **{name}** just hit **{tier['marks']:,} killmarks**! ({tier['prize']})",
        "allowed_mentions": NO_MENTIONS,
    }


def render_csv(counts, names, tiers):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["rank", "character", "character_id", "killmarks", "tier", "zkill"])
    for rank, (char, marks) in enumerate(_ranked(counts, names), start=1):
        writer.writerow([rank, _name(char, names), char, marks, current_tier(marks, tiers),
                         f"https://zkillboard.com/character/{char}/"])
    return out.getvalue()
