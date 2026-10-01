# Killmark Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A scheduled Python script that counts OPTM killmarks from zKillboard and keeps a Discord leaderboard (via webhook) up to date.

**Architecture:** Pure logic (counting, rendering) lives in small modules with no I/O; one HTTP module talks to zKill/ESI/Discord through an injectable `requests.Session`; `tracker.py` wires them together and persists JSON state in `data/`. GitHub Actions runs it every 30 minutes and commits `data/` back.

**Tech Stack:** Python 3.12 (works on 3.14 locally), `requests`, `pytest`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-01-killmark-tracker-design.md`

## Global Constraints

- Corp ID `98707560`; window `2026-10-01T00:00:00Z` ≤ t < `2026-11-01T00:00:00Z`.
- Tiers `[200, 500, 1000]` with emoji 🥉 🥈 🥇.
- Pod type IDs `{670, 33328}`.
- Blue alliances (initial): `99012654, 154104258, 99001317, 99005393, 99003581, 99013537, 99009129, 1727758877, 386292982, 99007203, 1042504553, 99002685, 498125261`.
- zKill URL: `https://zkillboard.com/api/kills/corporationID/{corp}/year/2026/month/10/page/{n}/`; ≥1 s between zKill requests; `User-Agent: OPTM-killmark-tracker (github actions)`.
- Only runtime dependency: `requests`. Dev: `pytest`.
- Discord embed description ≤ 4096 chars.
- Webhook URL comes only from env `DISCORD_WEBHOOK_URL`; never written to disk or logs.

## Review Focus

1. **Character listed twice on one mail, or attacker with no `character_id`** (NPC/structure) → counted once / ignored. Test in Task 1.
2. **Victim with no `alliance_id`** → not blue unless its corp is in `blue_corporations`. Test in Task 1.
3. **Window edges** → `2026-09-30T23:59:59Z` and `2026-11-01T00:00:00Z` excluded, `2026-10-31T23:59:59Z` included. Test in Task 1.
4. **Leaderboard message deleted in Discord** → PATCH 404 → new message posted and its ID saved. Test in Task 3.
5. **Too many participants for one embed** → lines trimmed, `+N more — full list in leaderboard.csv` appended, length ≤ 4096. Test in Task 2.

---

## File Structure

| File | Responsibility |
|---|---|
| `config.json` | Event settings, blues, DQ list, adjustments |
| `killmarks.py` | Pure: slim a killmail, count killmarks, tiers, tier-up detection |
| `render.py` | Pure: Discord leaderboard payload, tier-up text, CSV text |
| `sources.py` | HTTP: zKill paging, ESI fallback + names, Discord webhook post/edit |
| `tracker.py` | CLI orchestration and `data/` persistence |
| `data/killmails.json`, `data/state.json`, `data/leaderboard.csv` | Persisted state (created at runtime) |
| `.github/workflows/tracker.yml` | Schedule |
| `requirements.txt`, `README.md`, `.gitignore` | Setup |
| `tests/test_killmarks.py`, `tests/test_render.py`, `tests/test_sources.py` | Tests |

**Shared data shapes**

- *Slim killmail* (value in `data/killmails.json`, keyed by `str(killmail_id)`):
  `{"t": "2026-10-01T20:02:41Z", "ship": 11978, "vcorp": 635210548, "valli": 498125261 | null, "npc": false, "chars": [93895347, ...]}`
  `chars` = sorted distinct attacker `character_id`s whose `corporation_id == corp_id`.
- *Config* (`config.json`): `corporation_id`, `start` , `end` (ISO UTC strings), `tiers` (list of `{"marks": int, "emoji": str, "prize": str}`), `pod_type_ids`, `blue_alliances`, `blue_corporations`, `disqualified` (char IDs), `adjustments` (`{"<char_id>": int}`), `leaderboard_size`.
- *State* (`data/state.json`): `{"message_id": str | null, "counts": {"<char_id>": int}, "names": {"<char_id>": str}}`.

---

### Task 1: Counting rules

**Files:**
- Create: `config.json`, `killmarks.py`, `requirements.txt`, `.gitignore` (`__pycache__/`, `.pytest_cache/`, `.venv/`)
- Test: `tests/test_killmarks.py`

**Interfaces:**
- Produces:
  - `slim_killmail(km: dict, corp_id: int) -> dict` — full zKill/ESI mail → slim killmail.
  - `count_killmarks(slims: dict[str, dict], config: dict) -> dict[int, int]` — applies rules, then removes `disqualified`, then adds `adjustments`; drops entries ≤ 0.
  - `current_tier(marks: int, tiers: list[dict]) -> int` — number of tiers reached (0–3).
  - `detect_tier_ups(prev: dict[int, int], now: dict[int, int], tiers: list[dict]) -> list[tuple[int, int]]` — `(char_id, tier_index_reached)` for each char whose `current_tier` rose; one tuple per char, highest tier only; sorted by tier desc then char ID.

- [ ] **Step 1: Write failing tests** using a `make_km(time, victim_ship=587, victim_corp=1, victim_alli=2, npc=False, attackers=[(char, corp), ...])` helper and the real `config.json`:
  - `test_slim_keeps_only_corp_chars_deduped`: attackers `[(10, 98707560), (10, 98707560), (11, 555), (None, 98707560)]` → `chars == [10]`.
  - `test_counts_each_corp_char_once_per_mail`: two valid mails with chars `[10, 20]` and `[10]` → `{10: 2, 20: 1}`.
  - `test_pod_kills_excluded`: ship 670 and 33328 → `{}`.
  - `test_npc_excluded`.
  - `test_blue_alliance_excluded`: victim alliance `99003581` → `{}`; victim alliance `1354830081` (Goonswarm) → counted.
  - `test_blue_corporation_excluded`: config with `blue_corporations: [777]`, victim corp 777, no alliance → `{}`.
  - `test_victim_without_alliance_counts`: `valli None`, corp not blue → counted.
  - `test_window_edges`: `2026-09-30T23:59:59Z` ✗, `2026-10-01T00:00:00Z` ✓, `2026-10-31T23:59:59Z` ✓, `2026-11-01T00:00:00Z` ✗.
  - `test_disqualified_removed_even_with_adjustment`: DQ `[10]`, adjustments `{"10": 5}` → 10 absent.
  - `test_adjustments_apply_and_drop_nonpositive`: `{"20": 3, "30": -1}` with 20 at 1, 30 at 1 → `{20: 4}`.
  - `test_current_tier`: 199→0, 200→1, 999→2, 1000→3, 5000→3.
  - `test_tier_up_reports_highest_only`: prev `{1: 150}`, now `{1: 520, 2: 100}` → `[(1, 2)]`.
  - `test_tier_up_new_char`: prev `{}`, now `{3: 200}` → `[(3, 1)]`.

- [ ] **Step 2: Run** `python -m pytest tests/test_killmarks.py -v` — Expected: FAIL (`ModuleNotFoundError: killmarks`).
- [ ] **Step 3: Write `config.json`** with Global Constraints values; tier prizes copied from the spec table; `blue_corporations: []`, `disqualified: []`, `adjustments: {}`, `leaderboard_size: 50`. Add `requirements.txt` (`requests>=2.31`, `pytest>=8`).
- [ ] **Step 4: Implement `killmarks.py`.** Compare times as ISO strings parsed with `datetime.fromisoformat(s.replace("Z", "+00:00"))`.
- [ ] **Step 5: Run** `python -m pytest tests/test_killmarks.py -v` — Expected: all PASS.
- [ ] **Step 6: Commit** `feat: killmark counting rules and config`.

---

### Task 2: Rendering

**Files:**
- Create: `render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `current_tier` from Task 1.
- Produces:
  - `progress_line(rank: int, name: str, marks: int, tiers: list[dict]) -> str` — format `` `#3` **Name** — 612 ▰▰▰▰▰▰▱▱▱▱ 🥈 · 388 to 🥇 ``. Bar = 10 cells, filled = `floor(10 * (marks - prev_threshold) / (next - prev_threshold))` where prev_threshold is 0 below tier 1. Emoji of current tier shown only if tier ≥ 1. At tier 3: `` `#1` **Name** — 1,204 ▰▰▰▰▰▰▰▰▰▰ 🥇 MAX ``. Numbers use thousands separators.
  - `render_leaderboard(counts: dict[int, int], names: dict[int, str], config: dict, now: datetime) -> dict` — Discord webhook JSON `{"embeds": [{...}], "allowed_mentions": {"parse": []}}`. Sort by marks desc, then name. Title `☠️ October Killmark Challenge`; description = summary line `**{participants}** pilots · 🥉 {n1} · 🥈 {n2} · 🥇 {n3}` + blank line + ranked lines (top `leaderboard_size`), trimmed so description ≤ 4096 with `+N more — full list in leaderboard.csv`; footer `Updated {YYYY-MM-DD HH:MM} UTC · pods & blues excluded · leadership has final say`; color `0xB22222`. Empty counts → description `No killmarks yet — undock! o7`. Unknown names fall back to `Character {id}`.
  - `render_tier_up(name: str, tier: dict) -> dict` — `{"content": "{emoji} **{name}** just hit **{marks:,} killmarks**! ({prize})", "allowed_mentions": {"parse": []}}`.
  - `render_csv(counts, names, tiers) -> str` — header `rank,character,character_id,killmarks,tier,zkill`; zkill = `https://zkillboard.com/character/{id}/`; use `csv` module.

- [ ] **Step 1: Write failing tests:**
  - `test_progress_line_mid_tier`: 612 → contains `612`, `🥈`, `388 to 🥇`, `▰▰▰` count 2 (floor(10·112/500)=2).
  - `test_progress_line_below_first_tier`: 50 → `150 to 🥉`, 2 filled cells, no tier emoji before `·`.
  - `test_progress_line_max`: 1204 → `1,204` and `🥇 MAX`.
  - `test_leaderboard_sorted_and_summary`: counts `{1: 600, 2: 250, 3: 10}` → ranks in that order; summary shows `**3** pilots`, `🥉 2`, `🥈 1`, `🥇 0` (cumulative: reached at least that tier).
  - `test_leaderboard_trims_to_4096`: 300 chars with 40-char names, `leaderboard_size` 300 → description ≤ 4096 and ends with `full list in leaderboard.csv`.
  - `test_leaderboard_empty`.
  - `test_no_mentions_parsed`: name `@everyone` → `allowed_mentions == {"parse": []}`.
  - `test_csv_rows`: two chars → 3 lines, first data row rank 1.

- [ ] **Step 2: Run** `python -m pytest tests/test_render.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement `render.py`.**
- [ ] **Step 4: Run** `python -m pytest -v` — Expected: all PASS.
- [ ] **Step 5: Commit** `feat: Discord leaderboard and CSV rendering`.

---

### Task 3: HTTP sources

**Files:**
- Create: `sources.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `slim_killmail` from Task 1.
- Produces:
  - `make_session() -> requests.Session` — sets the User-Agent.
  - `fetch_new_killmails(session, corp_id: int, known_ids: set[str], sleep=time.sleep, max_pages: int = 50) -> list[dict]` — pages from 1; returns full mails not in `known_ids`; stops when a page is empty or contains no new IDs; calls `sleep(1)` between pages. Any mail missing `attackers` is replaced by ESI `GET https://esi.evetech.net/latest/killmails/{id}/{zkb.hash}/` merged with its `zkb`.
  - `resolve_names(session, char_ids: list[int]) -> dict[int, str]` — ESI `POST https://esi.evetech.net/latest/universe/names/` in chunks of 1000.
  - `post_or_edit(session, webhook_url: str, payload: dict, message_id: str | None) -> str` — if `message_id`: `PATCH {url}/messages/{id}`; on 404 fall through to POST. POST `{url}?wait=true`, return the response's `id`.
  - `send(session, webhook_url: str, payload: dict) -> None` — plain POST for tier-ups.
  - All requests go through one helper with 3 attempts, backoff `sleep(2**attempt)`, honoring `Retry-After` on 429; raises `requests.HTTPError` after the last attempt (404 on PATCH is returned, not retried).

- [ ] **Step 1: Write failing tests** with a `FakeSession` that records calls and returns queued `FakeResponse(status, json)` objects:
  - `test_fetch_stops_at_known_page`: known `{"1","2"}`; page 1 `[3,2]`, page 2 `[1]` → returns only mail 3, exactly two zKill GETs (stops after page 2 because it had no new IDs).
  - `test_fetch_stops_on_empty_page`.
  - `test_fetch_falls_back_to_esi_without_attackers`: mail lacking `attackers` → ESI URL called with its hash; returned mail has `attackers`.
  - `test_post_or_edit_patches_existing`: returns same id, PATCH URL ends `/messages/123`.
  - `test_post_or_edit_reposts_on_404`: PATCH 404 → POST with `?wait=true` → returns new id.
  - `test_retry_then_raise`: three 502s → `HTTPError`, `sleep` called twice or more.
- [ ] **Step 2: Run** `python -m pytest tests/test_sources.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement `sources.py`.**
- [ ] **Step 4: Run** `python -m pytest -v` — Expected: all PASS.
- [ ] **Step 5: Commit** `feat: zKill, ESI and Discord webhook clients`.

---

### Task 4: Orchestration and live dry run

**Files:**
- Create: `tracker.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `python tracker.py [--dry-run]`.

Flow of `main(argv) -> int`:
1. Load `config.json`, `data/killmails.json` (default `{}`), `data/state.json` (default `{"message_id": null, "counts": {}, "names": {}}`).
2. If not dry run and `DISCORD_WEBHOOK_URL` unset → print `DISCORD_WEBHOOK_URL is not set` and return 2.
3. `fetch_new_killmails` → slim each → merge into cache.
4. `count_killmarks`; resolve names for char IDs missing from `state["names"]`.
5. Write `data/killmails.json` and `data/leaderboard.csv` (JSON with `indent=1`, `sort_keys=True`).
6. Dry run: print the embed description and the tier-ups that would fire; return 0 without touching `state.json`.
7. Else: `post_or_edit` leaderboard; if `state["counts"]` was non-empty, `send` one `render_tier_up` per tier-up; save state with new `message_id`, `counts`, `names`; return 0.
8. HTTP failure anywhere → print the error (never the webhook URL) and return 1 before writing anything.

- [ ] **Step 1: Implement `tracker.py`.**
- [ ] **Step 2: Live dry run** `python tracker.py --dry-run` — Expected: prints a leaderboard of real OPTM pilots for Oct 1; `data/killmails.json` populated; no FRT/blue victims counted (spot-check: `python -c` that no slim with `valli` in blues contributes).
- [ ] **Step 3: Re-run** dry run — Expected: zKill fetch stops after page 1 (log line `fetched 0 new` or small number).
- [ ] **Step 4: Run** `python -m pytest -v` — all PASS.
- [ ] **Step 5: Commit** `feat: tracker CLI with dry-run` (include `data/killmails.json`).

---

### Task 5: Schedule and docs

**Files:**
- Create: `.github/workflows/tracker.yml`, `README.md`

- [ ] **Step 1: Workflow:** triggers `schedule: cron "*/30 * * * *"` and `workflow_dispatch`; `permissions: contents: write`; `concurrency: killmark-tracker` (no cancel); steps: checkout, setup-python 3.12 with pip cache, `pip install -r requirements.txt`, `python -m pytest -q`, `python tracker.py` with `DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}`, then commit `data/` as `github-actions[bot]` only if `git status --porcelain data` is non-empty, `git push`.
- [ ] **Step 2: README:** what it does (rules summary), setup (create GitHub repo — private recommended; push; add secret `DISCORD_WEBHOOK_URL` from Discord channel → Integrations → Webhooks; run workflow once manually), leadership editing guide (blues, DQ, adjustments with examples), where the CSV is, how to stop it in November.
- [ ] **Step 3: Validate YAML** `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/tracker.yml'))"` (skip if PyYAML missing; then eyeball) — Expected: no error.
- [ ] **Step 4: Commit** `chore: GitHub Actions schedule and README`.
