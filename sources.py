"""HTTP clients for zKillboard, ESI and the Discord webhook."""
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


def fetch_new_killmails(session, corp_id, known_ids, sleep=time.sleep, max_pages=50):
    """Full killmails from zKill not in `known_ids`, newest first."""
    new = []
    for page in range(1, max_pages + 1):
        if page > 1:
            sleep(1)
        url = ZKILL_URL.format(corp=corp_id, page=page)
        mails = _request(session, "GET", url, f"zKillboard page {page}", sleep).json() or []
        fresh = [m for m in mails if str(m["killmail_id"]) not in known_ids]
        for m in fresh:
            if "attackers" not in m:
                m.update(_esi_killmail(session, m, sleep))
        new.extend(fresh)
        if not fresh:
            break
    return new


def _esi_killmail(session, mail, sleep):
    url = ESI_KILLMAIL_URL.format(id=mail["killmail_id"], hash=mail["zkb"]["hash"])
    return _request(session, "GET", url, f"ESI killmail {mail['killmail_id']}", sleep).json()


def resolve_names(session, char_ids, sleep=time.sleep):
    names = {}
    ids = sorted(set(char_ids))
    for i in range(0, len(ids), 1000):
        resp = _request(session, "POST", ESI_NAMES_URL, "ESI names", sleep, json=ids[i:i + 1000])
        names.update({entry["id"]: entry["name"] for entry in resp.json()})
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
