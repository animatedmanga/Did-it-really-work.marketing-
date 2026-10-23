import pytest
import requests

from measurement import audit
from measurement.audit import SAMPLE_PAGES, audit_html, detect_signals, fetch_html


def scored(name):
    url, html = SAMPLE_PAGES[name]
    return audit_html(html, url)


def test_sample_scores_increase_with_maturity():
    basic = scored("Basic: direct tag only")
    typical = scored("Typical: Tag Manager with consent platform")
    modern = scored("Modern: consent v2, enhanced conversions, server-side")
    assert basic.score < typical.score < modern.score
    assert basic.grade == "Exposed"
    assert modern.grade == "Resilient"
    assert modern.score >= 80


def test_scores_are_bounded_and_weights_sum_to_100():
    for name in SAMPLE_PAGES:
        result = scored(name)
        assert 0 <= result.score <= 100
        assert sum(c.weight for c in result.checks) == 100


def test_detects_expected_signals_on_modern_page():
    url, html = SAMPLE_PAGES["Modern: consent v2, enhanced conversions, server-side"]
    s = detect_signals(html, url)
    assert s["consent_default"] and s["consent_v2_params"]
    assert s["enhanced_conversions"]
    assert s["server_side"]
    assert "metrics.example.com" in s["custom_loader_hosts"]
    assert s["ga4_ids"] == ["G-TEST123456"]
    assert s["ads_ids"] == ["AW-123456789"]
    assert "OneTrust" in s["cmps"]


def test_ad_user_data_is_not_mistaken_for_enhanced_conversions():
    html = "<script>gtag('consent','default',{ad_user_data:'denied',ad_personalization:'denied'});</script>"
    assert detect_signals(html)["enhanced_conversions"] is False


def test_legacy_and_duplicate_tags_reduce_hygiene_score():
    html = (
        "<script src='https://www.googletagmanager.com/gtm.js?id=GTM-ABCD123'></script>"
        "<script src='https://www.googletagmanager.com/gtag/js?id=G-AAAAAA1111'></script>"
        "<script>gtag('config','G-BBBBBB2222'); gtag('config','UA-1234567-1');</script>"
    )
    result = audit_html(html, "https://example.com")
    hygiene = next(c for c in result.checks if c.name == "Tag hygiene")
    assert hygiene.points == 0
    assert hygiene.status == "fail"


def test_gtm_only_page_reports_unverifiable_items_with_no_credit():
    url, html = SAMPLE_PAGES["Typical: Tag Manager with consent platform"]
    result = audit_html(html, url)
    by_name = {c.name: c for c in result.checks}
    assert by_name["Enhanced conversions"].status == "unverifiable"
    assert by_name["Enhanced conversions"].points == 0


def test_user_confirmation_upgrades_unverifiable_items():
    url, html = SAMPLE_PAGES["Typical: Tag Manager with consent platform"]
    before = audit_html(html, url)
    after = audit_html(html, url, confirmed={"Enhanced conversions"})
    assert after.score == before.score + 25
    assert next(c for c in after.checks if c.name == "Enhanced conversions").status == "pass"


def test_empty_page_fails_foundation():
    result = audit_html("<html><body>Hello</body></html>", "https://example.com")
    assert result.checks[0].status == "fail"
    assert result.grade == "Exposed"


def test_priorities_are_ordered_by_recoverable_points():
    result = scored("Basic: direct tag only")
    gaps = [c.weight - c.points for c in result.priorities()]
    assert gaps == sorted(gaps, reverse=True)


# ---- fetching and SSRF protection ---------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "ftp://example.com/",
        "not a url",
    ],
)
def test_fetch_rejects_unsafe_targets(url):
    with pytest.raises(ValueError):
        fetch_html(url)


class FakeResponse:
    def __init__(self, status=200, body=b"<html>ok</html>", headers=None):
        self.status_code = status
        self.is_redirect = status in {301, 302, 303, 307, 308}
        self.headers = headers or {}
        self.encoding = "utf-8"
        self._body = body

    def iter_content(self, chunk_size=1):
        yield self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def close(self):
        pass


def test_fetch_returns_body_for_public_host(monkeypatch):
    monkeypatch.setattr(audit.requests, "get", lambda *a, **k: FakeResponse())
    html, final = fetch_html("http://93.184.216.34/")
    assert html == "<html>ok</html>"
    assert final == "http://93.184.216.34/"


def test_fetch_blocks_redirect_to_private_address(monkeypatch):
    monkeypatch.setattr(
        audit.requests,
        "get",
        lambda *a, **k: FakeResponse(302, headers={"Location": "http://127.0.0.1/admin"}),
    )
    with pytest.raises(ValueError, match="publicly routable"):
        fetch_html("http://93.184.216.34/")


def test_fetch_limits_redirect_chain(monkeypatch):
    monkeypatch.setattr(
        audit.requests,
        "get",
        lambda *a, **k: FakeResponse(302, headers={"Location": "http://93.184.216.34/next"}),
    )
    with pytest.raises(ValueError, match="Too many redirects"):
        fetch_html("http://93.184.216.34/")
