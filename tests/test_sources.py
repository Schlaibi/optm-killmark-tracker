import pytest
import requests

from sources import fetch_new_killmails, post_or_edit, resolve_names, send, send_all

WEBHOOK = "https://discord.com/api/webhooks/1/token"


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def km(kid, attackers=True):
    m = {"killmail_id": kid, "killmail_time": "2026-10-01T12:00:00Z",
         "victim": {"ship_type_id": 587}, "zkb": {"hash": f"h{kid}", "npc": False}}
    if attackers:
        m["attackers"] = [{"character_id": 1, "corporation_id": 98707560}]
    return m


def no_sleep(_):
    pass


def test_fetch_stops_at_known_page():
    session = FakeSession([FakeResponse(body=[km(3), km(2)]), FakeResponse(body=[km(1)])])
    result = fetch_new_killmails(session, 98707560, {"1", "2"}, sleep=no_sleep)
    assert [m["killmail_id"] for m in result] == [3]
    assert len(session.calls) == 2
    assert session.calls[0][1].endswith("/corporationID/98707560/year/2026/month/10/page/1/")


def test_fetch_stops_on_empty_page():
    session = FakeSession([FakeResponse(body=[km(5)]), FakeResponse(body=[])])
    result = fetch_new_killmails(session, 98707560, set(), sleep=no_sleep)
    assert [m["killmail_id"] for m in result] == [5]
    assert len(session.calls) == 2


def test_fetch_falls_back_to_esi_without_attackers():
    esi_mail = km(9)
    del esi_mail["zkb"]
    session = FakeSession([
        FakeResponse(body=[km(9, attackers=False)]),
        FakeResponse(body=esi_mail),
        FakeResponse(body=[]),
    ])
    result = fetch_new_killmails(session, 98707560, set(), sleep=no_sleep)
    assert session.calls[1][1] == "https://esi.evetech.net/latest/killmails/9/h9/"
    assert result[0]["attackers"] and result[0]["zkb"]["hash"] == "h9"


def test_post_or_edit_patches_existing():
    session = FakeSession([FakeResponse(body={"id": "123"})])
    assert post_or_edit(session, WEBHOOK, {"content": "x"}, "123", sleep=no_sleep) == "123"
    method, url, _ = session.calls[0]
    assert method == "PATCH" and url == WEBHOOK + "/messages/123"


def test_post_or_edit_reposts_on_404():
    session = FakeSession([FakeResponse(status=404), FakeResponse(body={"id": "456"})])
    assert post_or_edit(session, WEBHOOK, {"content": "x"}, "123", sleep=no_sleep) == "456"
    method, url, _ = session.calls[1]
    assert method == "POST" and url == WEBHOOK + "?wait=true"


def test_post_or_edit_first_run_posts():
    session = FakeSession([FakeResponse(body={"id": "789"})])
    assert post_or_edit(session, WEBHOOK, {"content": "x"}, None, sleep=no_sleep) == "789"
    assert session.calls[0][0] == "POST"


def test_retry_then_raise():
    sleeps = []
    session = FakeSession([FakeResponse(status=502)] * 3)
    with pytest.raises(requests.HTTPError):
        send(session, WEBHOOK, {"content": "x"}, sleep=sleeps.append)
    assert len(session.calls) == 3 and len(sleeps) >= 2


def test_retry_honors_retry_after():
    sleeps = []
    session = FakeSession([FakeResponse(status=429, headers={"Retry-After": "7"}), FakeResponse(status=204)])
    send(session, WEBHOOK, {"content": "x"}, sleep=sleeps.append)
    assert sleeps == [7.0]


class ExplodingSession(FakeSession):
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")


@pytest.mark.parametrize("session", [
    FakeSession([FakeResponse(status=500)] * 3),
    ExplodingSession([]),
])
def test_errors_do_not_leak_webhook_token(session):
    with pytest.raises(requests.RequestException) as err:
        send(session, WEBHOOK, {"content": "x"}, sleep=no_sleep)
    assert "token" not in str(err.value)


def test_full_sweep_finds_late_mail_behind_known_page():
    session = FakeSession([
        FakeResponse(body=[km(5), km(4)]),
        FakeResponse(body=[km(3), km(2)]),
        FakeResponse(body=[]),
    ])
    result = fetch_new_killmails(session, 98707560, {"5", "4", "2"}, sleep=no_sleep, full=True)
    assert [m["killmail_id"] for m in result] == [3]
    assert len(session.calls) == 3


def test_max_pages_warns(capsys):
    session = FakeSession([FakeResponse(body=[km(i)]) for i in range(10, 7, -1)])
    result = fetch_new_killmails(session, 98707560, set(), sleep=no_sleep, max_pages=3)
    assert len(result) == 3
    assert "max_pages" in capsys.readouterr().err


def test_resolve_names_skips_invalid_ids():
    session = FakeSession([
        FakeResponse(status=404, body={"error": "Ensure all IDs are valid before resolving."}),
        FakeResponse(status=404),
        FakeResponse(body=[{"id": 2115722344, "name": "Real Pilot", "category": "character"}]),
    ])
    assert resolve_names(session, [2115722344, 1], sleep=no_sleep) == {2115722344: "Real Pilot"}


def test_send_all_paces_and_survives_failures():
    sleeps = []
    session = FakeSession([FakeResponse(status=400), FakeResponse(status=204)])
    failures = send_all(session, WEBHOOK, [{"content": "a"}, {"content": "b"}], sleep=sleeps.append)
    assert failures == 1
    assert len(session.calls) == 2 and 1 in sleeps
