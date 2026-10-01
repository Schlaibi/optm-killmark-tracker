# October Killmark Challenge Tracker — Design

**Date:** 2026-10-01
**Status:** Approved in chat; awaiting written-spec review

## Goal

Give Optimistic Wasteland Inc. [OPTM.] members a live Discord leaderboard for the
October Killmark Challenge, showing each character's killmark count and how far
they are from the reward tiers (200 / 500 / 1,000). Give leadership a full
export for the final manual review before prizes go out.

## Fixed facts

| Item | Value |
|---|---|
| Corporation | Optimistic Wasteland Inc. [OPTM.] — ID `98707560` |
| Alliance | Fraternity. [FRT] — ID `99003581` |
| Event window | 2026-10-01 00:00:00 UTC ≤ killmail_time < 2026-11-01 00:00:00 UTC |
| Tiers | 200 (Marauder), 500 (BLOPS + Cyno Cruiser), 1,000 (Revelation + T1 Carrier) |
| Data source | `https://zkillboard.com/api/kills/corporationID/98707560/year/2026/month/10/page/{n}/` |

The zKillboard endpoint was verified on 2026-10-01 to return full killmails
(`killmail_id`, `killmail_time`, `victim`, `attackers`, `zkb`), newest first,
and only mails where an OPTM character is an attacker.

## Counting rules

A killmail counts if **all** hold:

1. `killmail_time` is inside the event window.
2. Victim ship is not a capsule (`ship_type_id` not in `{670, 33328}`).
3. `zkb.npc` is false.
4. Victim `alliance_id` is not in `blue_alliances` and victim `corporation_id`
   is not in `blue_corporations` (see config).

For each counting mail, **every distinct attacker character whose
`corporation_id` on that mail is `98707560`** gets +1. Membership is judged at
kill time (from the mail), so someone joining mid-month counts only from then.
Characters are counted separately (no alt merging).

After counting: characters in `disqualified` are removed, then
`adjustments` (char ID → signed integer) are added.

Farming/staged-kill detection is **out of scope**; leadership reviews the CSV.

## Initial blue list (`blue_alliances`)

| ID | Ticker | Name |
|---|---|---|
| 99012654 | -ANT- | Ant Tiger |
| 154104258 | APOC | Apocalypse Now. |
| 99001317 | .RU | Banderlogs Alliance |
| 99005393 | 2GTHR | Blades of Grass |
| 99003581 | FRT | Fraternity. |
| 99013537 | EVIL. | Insidious. |
| 99009129 | NO | No Visual. |
| 1727758877 | NC | Northern Coalition. |
| 386292982 | -10.0 | Pandemic Legion |
| 99007203 | SB-SQ | Siberian Squads |
| 1042504553 | SLYCE | Solyaris Chtonium |
| 99002685 | SYN | Synergy of Steel |
| 498125261 | TEST | Test Alliance Please Ignore |

Goonswarm is **not** blue; kills on Goons count.

## Components

- **`tracker.py`** — single entry point, split into small pure functions:
  - `fetch_new_killmails(cache)` — pages zKill until a page is empty or every
    mail on it is already cached; 1 s between requests; descriptive
    `User-Agent`. If a mail lacks `attackers`, fall back to ESI
    `/killmails/{id}/{hash}/`.
  - `count_killmarks(killmails, config) -> {char_id: count}` — pure; applies
    the rules above.
  - `resolve_names(char_ids)` — ESI `POST /universe/names/` in batches of 1000,
    cached.
  - `render_leaderboard(counts, names, config, now) -> discord payload` — pure.
  - `detect_tier_ups(prev_counts, counts, tiers)` — pure.
  - `post_or_edit(webhook_url, payload, message_id)` — creates the message on
    first run (`?wait=true` to get its ID), afterwards `PATCH
    /messages/{id}`. If the PATCH returns 404 (message deleted), post a new one.
  - CLI: `python tracker.py [--dry-run]`. Dry run prints the board, posts nothing,
    writes nothing to `data/discord.json`.
- **`config.json`** — corp/alliance IDs, window, tiers, `blue_alliances`,
  `blue_corporations`, `disqualified`, `adjustments`, `leaderboard_size` (50).
- **`data/killmails.json`** — slim cache: per killmail ID store time, victim
  ship/corp/alliance, `npc`, and the list of OPTM attacker char IDs. Counting
  is recomputed from this every run, so config edits apply retroactively.
- **`data/state.json`** — Discord message ID, last counts (for tier-up
  detection), character name cache.
- **`data/leaderboard.csv`** — rank, character, char ID, killmarks, tier,
  zKill character link. Full list, for leadership review.
- **`.github/workflows/tracker.yml`** — cron `*/30 * * * *` plus
  `workflow_dispatch`; Python 3.12; runs tracker; commits `data/` back if
  changed. Secret: `DISCORD_WEBHOOK_URL`.
- **`tests/`** — pytest for `count_killmarks`, `render_leaderboard`,
  `detect_tier_ups`, using small fixture killmails shaped like real zKill data.
- **`README.md`** — setup steps and how leadership edits config.

## Discord output

**Leaderboard message** (one embed, edited in place each run):

- Title: `☠️ October Killmark Challenge`
- Summary line: participants, counted mails, characters at 🥉/🥈/🥇.
- Ranked lines, top `leaderboard_size`:
  `` `#3` **Pilot Name** — 612 ▰▰▰▰▰▰▱▱▱▱ 🥈 · 388 to 🥇 ``
  Bar shows progress toward the next tier; at 1,000+ shows `🥇 MAX`.
- Footer: `Updated <UTC time> · pod kills & blues excluded · leadership has final say`.
- If the description would exceed Discord's 4,096-char embed limit, trim lines
  and append `+N more — full list in leaderboard.csv`.

**Tier-up posts:** for each character whose count crossed a tier since the last
run, a short new message, e.g. `🥉 **Pilot Name** just hit **200 killmarks**!`
Not sent on the very first run (to avoid a burst) and never in dry run.

## Lifecycle

- Every 30 min during October (GitHub may delay runs 5–15 min).
- Mails stay on zKill under `month/10`, so late-posted October mails are
  still picked up in early November runs.
- Leadership disables the workflow once prizes are settled.

## Error handling

- zKill/ESI HTTP errors: retry 3× with backoff; if still failing, exit non-zero
  without touching the Discord message (Actions shows the failed run; next run
  retries).
- Missing `DISCORD_WEBHOOK_URL` and not dry run: exit with a clear message.
- Cache and state are written only after a successful fetch.

## Out of scope

Slash commands, alt linking, automatic farming detection, a web dashboard.
