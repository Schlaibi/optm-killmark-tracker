# ☠️ October Killmark Challenge Tracker

Keeps a live leaderboard in Discord for the OPTM October Killmark Challenge.
Every 30 minutes it pulls Optimistic Wasteland Inc. [OPTM.] kills from
zKillboard, counts killmarks per character, and edits one leaderboard message
in your channel. When a pilot crosses 🥉 200 / 🥈 500 / 🥇 1,000 it posts a short shout-out.

## What counts

A killmail gives **+1 to every OPTM character on it** when:

- it happened between **Oct 1 00:00 and Oct 31 23:59:59 EVE time (UTC)**;
- the victim is **not a pod** (Capsule / Genolution capsule);
- it is **not an NPC kill**;
- the victim's alliance or corp is **not on the blue list** in `config.json`.

Characters count separately (no alt merging), and a pilot counts only on mails
from while they were in OPTM. Farming, staged kills and other abuse are **not**
detected automatically — that's leadership's review, using `data/leaderboard.csv`.

## Setup (one time, ~5 minutes)

1. **Create a Discord webhook:** Channel settings → Integrations → Webhooks →
   New Webhook → pick the leaderboard channel → **Copy Webhook URL**.
   Treat this URL like a password.
2. **Create a GitHub repository** and push this folder. A **public** repo gets
   unlimited free Actions minutes (everything in it is public zKillboard data
   anyway, plus the blue list). A **private** repo works too, but the 30-minute
   schedule uses roughly 1,500 of the 2,000 free minutes per month — if you go
   private, check *Settings → Billing* mid-month, and change the cron in
   `.github/workflows/tracker.yml` to `"0 * * * *"` (hourly) if it's running low.
   ```bash
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. In the repo: **Settings → Secrets and variables → Actions → New repository secret**,
   name `DISCORD_WEBHOOK_URL`, value = the webhook URL.
4. **Actions tab → Killmark tracker → Run workflow** once. The leaderboard message
   appears in Discord; from then on it updates itself every ~30 minutes
   (GitHub can delay scheduled runs by 5–15 minutes when it's busy).

Tip: pin the leaderboard message in the channel.

## For leadership: editing `config.json`

Edit the file on GitHub (pencil icon) and commit. The next run recalculates
everything from scratch, so changes apply to the whole month.

| Field | What it does | Example |
|---|---|---|
| `blue_alliances` | Alliance IDs whose losses don't count | `99003581` (FRT) |
| `blue_corporations` | Same, for single corps | `[98000001]` |
| `disqualified` | Character IDs removed from the board | `[2112345678]` |
| `adjustments` | Manual +/- killmarks per character ID | `{"2112345678": -25}` |
| `leaderboard_size` | How many pilots show in Discord | `50` |

Find an ID from the zKillboard URL, e.g. `zkillboard.com/character/2112345678/`
or `zkillboard.com/alliance/99003581/`.

The full ranked list with zKillboard links is in **`data/leaderboard.csv`**
(open it on GitHub, or download it into a spreadsheet) for the final review.

## When October is over

Mails sometimes reach zKillboard hours late. Every 6 hours (and on every run
after Oct 31) the tracker re-scans all of October to catch them; you can force
one with **Actions → Killmark tracker → Run workflow → full**. Before handing
out prizes, run one full scan and use that `leaderboard.csv`. After prizes go out,
go to **Actions → Killmark tracker → ⋯ → Disable workflow**. The last
leaderboard stays in Discord.

## Running locally

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m pytest
.venv/Scripts/python tracker.py --dry-run
```

`--dry-run` prints the leaderboard instead of posting it.
