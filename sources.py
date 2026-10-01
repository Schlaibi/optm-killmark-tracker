"""HTTP clients for zKillboard, ESI and the Discord webhook."""
import sys
import time

import requests

USER_AGENT = "OPTM-killmark-tracker (github actions)"
ZKILL_URL = "https://zkillboard.com/api/kills/corporationID/{corp}/year/2026/month/10/page/{page}/"
ESI_KILLMAIL_URL = "https://esi.evetech.net/latest/killmails/{id}/{hash}/"
ESI_NAMES_URL = "https://esi.evetech.net/latest/universe/names/"
ATTEMPTS = 3
TIMEOUT = 30


def make_session():
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _request(session, method, url, label, sleep, allow=(), **kwargs):
    """Request with retries on 429/5xx/network errors.

    Errors name only `label`, never the URL, so the webhook token can't reach logs.
    Statuses in `allow` are returned instead of raised.
    """
    for attempt in range(ATTEMPTS):
        last = attempt == ATTEMPTS - 1
        try:
            resp = session.request(method, url, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as e:
            if last:
                raise requests.RequestException(f"{label} failed: {type(e).__name__}") from None
            sleep(2 ** attempt)
            continue
        if resp.status_code in allow or resp.status_code < 400:
            return resp
        if resp.status_code == 429 or resp.status_code >= 500:
            if not last:
                sleep(float(resp.headers.get("Retry-After", 2 ** attempt)))
                continue
        raise requests.HTTPError(f"{label} failed: HTTP {resp.status_code}", response=resp)


def fetch_new_killmails(session, corp_id, known_ids, sleep=time.sleep, max_pages=100, full=False):
    """Full killmails from zKill not in `known_ids`, newest first.

    Normally stops at the first page with nothing new. `full` pages to the end, which
    catches mails that reached zKill late and sort below already-known ones.
    """
    new = []
    for page in range(1, max_pages + 1):
        if page > 1:
            sleep(1)
        url = ZKILL_URL.format(corp=corp_id, page=page)
        mails = _request(session, "GET", url, f"zKillboard page {page}", sleep).json() or []
        if not mails:
            return new
        fresh = [m for m in mails if str(m["killmail_id"]) not in known_ids]
        for m in fresh:
            if "attackers" not in m:
                m.update(_esi_killmail(session, m, sleep))
        new.extend(fresh)
        if not fresh and not full:
            return new
    print(f"warning: stopped at max_pages={max_pages}; older mails may be missing", file=sys.stderr)
    return new


def _esi_killmail(session, mail, sleep):
    url = ESI_KILLMAIL_URL.format(id=mail["killmail_id"], hash=mail["zkb"]["hash"])
    return _request(session, "GET", url, f"ESI killmail {mail['killmail_id']}", sleep).json()


def resolve_names(session, char_ids, sleep=time.sleep):
    """{id: name}. ESI rejects a whole batch over one bad ID, so on 404 retry IDs one by one and skip bad ones."""
    names = {}
    ids = sorted(set(char_ids))
    for i in range(0, len(ids), 1000):
        names.update(_names(session, ids[i:i + 1000], sleep))
    return names


def _names(session, ids, sleep):
    resp = _request(session, "POST", ESI_NAMES_URL, "ESI names", sleep, allow=(404,), json=ids)
    if resp.status_code != 404:
        return {entry["id"]: entry["name"] for entry in resp.json()}
    if len(ids) == 1:
        print(f"warning: ESI doesn't know character ID {ids[0]}", file=sys.stderr)
        return {}
    names = {}
    for char_id in ids:
        names.update(_names(session, [char_id], sleep))
    return names


def post_or_edit(session, webhook_url, payload, message_id, sleep=time.sleep):
    """Edit the leaderboard message in place; post a new one if it doesn't exist. Returns its ID."""
    base = webhook_url.rstrip("/")
    if message_id:
        resp = _request(session, "PATCH", f"{base}/messages/{message_id}", "Discord edit", sleep,
                        allow=(404,), json=payload)
        if resp.status_code != 404:
            return message_id
    resp = _request(session, "POST", f"{base}?wait=true", "Discord post", sleep, json=payload)
    return str(resp.json()["id"])


def send(session, webhook_url, payload, sleep=time.sleep):
    _request(session, "POST", webhook_url.rstrip("/"), "Discord post", sleep, json=payload)


def send_all(session, webhook_url, payloads, sleep=time.sleep):
    """Post each payload ~1 s apart; a failed post is logged and skipped. Returns the failure count."""
    failures = 0
    for i, payload in enumerate(payloads):
        if i:
            sleep(1)
        try:
            send(session, webhook_url, payload, sleep)
        except requests.RequestException as e:
            print(f"warning: {e}", file=sys.stderr)
            failures += 1
    return failures
