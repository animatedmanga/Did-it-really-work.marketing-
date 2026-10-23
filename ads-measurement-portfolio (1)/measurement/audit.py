"""Measurement readiness audit (Project 4).

Inspects the HTML of a page for signals that indicate how resilient its ad
measurement is to privacy changes and signal loss: Google tag setup, Consent
Mode v2, enhanced conversions, first-party or server-side tagging, and basic tag
hygiene.

Important limitation: this is a static check of page source. Settings that live
inside a Tag Manager container, and anything injected after page load, cannot be
seen here. Such items are reported as "unverifiable" and earn no credit until
the user confirms them.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests

GOOGLE_HOSTS = {"www.googletagmanager.com", "googletagmanager.com"}

CMP_SIGNATURES = {
    "Cookiebot": "cookiebot.com",
    "OneTrust": "cookielaw.org",
    "Osano": "osano.com",
    "Usercentrics": "usercentrics.eu",
    "TrustArc": "trustarc.com",
    "iubenda": "iubenda.com",
    "Didomi": "didomi.io",
    "CookieYes": "cookieyes.com",
    "Termly": "termly.io",
    "consentmanager": "consentmanager.net",
}

OTHER_PIXELS = {
    "Meta pixel": "connect.facebook.net",
    "TikTok pixel": "analytics.tiktok.com",
    "LinkedIn Insight": "snap.licdn.com",
    "X (Twitter) pixel": "static.ads-twitter.com",
    "Pinterest tag": "s.pinimg.com/ct/core.js",
}

_GTM_ID = re.compile(r"\bGTM-[A-Z0-9]{4,8}\b")
_GA4_ID = re.compile(r"\bG-[A-Z0-9]{6,14}\b")
_AW_ID = re.compile(r"\bAW-\d{6,12}\b")
_UA_ID = re.compile(r"\bUA-\d{4,10}-\d{1,3}\b")
_GTM_SCRIPT_HOST = re.compile(r"""<script[^>]+src=["'](?:https?:)?//([^/"']+)/[^"']*gtm\.js""", re.I)
_GTM_INLINE_HOST = re.compile(r"""\.src\s*=\s*["']https?://([^/"']+)/gtm\.js""", re.I)
_GTAG_SCRIPT = re.compile(r"""<script[^>]+src=["'](?:https?:)?//([^/"']+)/gtag/js\?id=([A-Za-z0-9-]+)""", re.I)
_CONSENT_DEFAULT = re.compile(r"""["']consent["']\s*,\s*["']default["']""")
_EC_MARKERS = re.compile(
    r"""allow_enhanced_conversions|enhanced_conversions|["']set["']\s*,\s*["']user_data["']""", re.I
)

STATUS_CREDIT = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "unverifiable": 0.0}


@dataclass
class Check:
    name: str
    status: str
    weight: int
    points: float
    finding: str
    recommendation: str


@dataclass
class AuditResult:
    url: str
    score: float
    grade: str
    checks: list[Check] = field(default_factory=list)
    signals: dict = field(default_factory=dict)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Check": c.name,
                    "Status": c.status,
                    "Points": round(c.points, 1),
                    "Out of": c.weight,
                    "Finding": c.finding,
                    "Recommendation": c.recommendation,
                }
                for c in self.checks
            ]
        )

    def priorities(self) -> list[Check]:
        """Checks that lost points, ordered by the points available to recover."""
        open_items = [c for c in self.checks if c.points < c.weight]
        return sorted(open_items, key=lambda c: c.weight - c.points, reverse=True)


def detect_signals(html: str, url: str = "") -> dict:
    """Extract measurement signals from page source."""
    lower = html.lower()
    gtm_hosts = set(_GTM_SCRIPT_HOST.findall(html)) | set(_GTM_INLINE_HOST.findall(html))
    gtag_loaders = _GTAG_SCRIPT.findall(html)
    gtag_hosts = {host for host, _ in gtag_loaders}

    custom_hosts = {h for h in gtm_hosts | gtag_hosts if h.lower() not in GOOGLE_HOSTS}
    server_side_config = "server_container_url" in lower or "transport_url" in lower

    cmps = [name for name, sig in CMP_SIGNATURES.items() if sig in lower]
    other = [name for name, sig in OTHER_PIXELS.items() if sig in lower]

    return {
        "https": urlparse(url).scheme == "https" if url else None,
        "gtm_ids": sorted(set(_GTM_ID.findall(html))),
        "ga4_ids": sorted(set(_GA4_ID.findall(html))),
        "ads_ids": sorted(set(_AW_ID.findall(html))),
        "legacy_ua_ids": sorted(set(_UA_ID.findall(html))),
        "has_gtm": bool(gtm_hosts) or bool(_GTM_ID.search(html)),
        "has_gtag_loader": bool(gtag_loaders),
        "consent_default": bool(_CONSENT_DEFAULT.search(html)),
        "consent_v2_params": "ad_user_data" in lower and "ad_personalization" in lower,
        "cmps": cmps,
        "enhanced_conversions": bool(_EC_MARKERS.search(html)),
        "custom_loader_hosts": sorted(custom_hosts),
        "server_side": bool(custom_hosts) or server_side_config,
        "other_pixels": other,
    }


def _grade(score: float) -> str:
    if score >= 80:
        return "Resilient"
    if score >= 50:
        return "Partially resilient"
    return "Exposed"


def _make(name: str, status: str, weight: int, finding: str, recommendation: str, points: float | None = None) -> Check:
    earned = STATUS_CREDIT[status] * weight if points is None else points
    return Check(name, status, weight, earned, finding, recommendation)


def audit_html(html: str, url: str = "", confirmed: set[str] | None = None) -> AuditResult:
    """Score a page. `confirmed` lists unverifiable checks the user verified elsewhere."""
    confirmed = confirmed or set()
    s = detect_signals(html, url)
    has_google_tag = s["has_gtm"] or s["has_gtag_loader"]
    gtm_only = s["has_gtm"] and not s["has_gtag_loader"]
    checks: list[Check] = []

    # 1. Foundation
    if has_google_tag:
        ids = ", ".join(s["gtm_ids"] + s["ga4_ids"] + s["ads_ids"]) or "tag present"
        checks.append(_make("Google tag foundation", "pass", 15, f"Detected: {ids}.", "No action required."))
    else:
        checks.append(
            _make(
                "Google tag foundation",
                "fail",
                15,
                "No Google tag or Tag Manager container detected in page source.",
                "Deploy the Google tag or a Tag Manager container so that conversion and audience signals can be collected.",
            )
        )

    # 2. Consent Mode v2
    consent_name = "Consent Mode v2"
    if s["consent_default"] and s["consent_v2_params"]:
        checks.append(_make(consent_name, "pass", 25, "Default consent state with v2 parameters detected.", "Confirm that consent updates fire after the user chooses."))
    elif s["consent_default"]:
        checks.append(
            _make(
                consent_name,
                "partial",
                25,
                "A default consent state was found but the v2 parameters ad_user_data and ad_personalization are missing.",
                "Add ad_user_data and ad_personalization to the default and update calls.",
            )
        )
    elif s["cmps"] and not gtm_only:
        checks.append(
            _make(
                consent_name,
                "partial",
                25,
                f"Consent platform detected ({', '.join(s['cmps'])}) but no default consent state is visible.",
                "Confirm the consent platform sends Consent Mode signals before tags fire.",
            )
        )
    elif has_google_tag and (gtm_only or s["cmps"]):
        status = "pass" if consent_name in confirmed else "unverifiable"
        checks.append(
            _make(
                consent_name,
                status,
                25,
                "Consent configuration may live inside the Tag Manager container and is not visible in page source."
                if status == "unverifiable"
                else "Confirmed by the user in the Tag Manager container.",
                "Open the container and verify that a consent default and a consent platform template are in place.",
            )
        )
    else:
        checks.append(
            _make(
                consent_name,
                "fail",
                25,
                "No consent signals or consent platform detected.",
                "Implement a certified consent platform and Consent Mode v2 so that modeling can recover conversions from unconsented traffic.",
            )
        )

    # 3. Enhanced conversions
    ec_name = "Enhanced conversions"
    if s["enhanced_conversions"]:
        checks.append(_make(ec_name, "pass", 25, "Enhanced conversion markers detected.", "Validate match rate in the Google Ads diagnostics."))
    elif gtm_only:
        status = "pass" if ec_name in confirmed else "unverifiable"
        checks.append(
            _make(
                ec_name,
                status,
                25,
                "Enhanced conversions are configured in the container if at all, so they cannot be seen in page source."
                if status == "unverifiable"
                else "Confirmed by the user in the Tag Manager container.",
                "Check the conversion tag settings for user-provided data and confirm the diagnostics report is healthy.",
            )
        )
    else:
        checks.append(
            _make(
                ec_name,
                "fail",
                25,
                "No enhanced conversion markers detected.",
                "Enable enhanced conversions with hashed first-party data to recover conversions lost to cookie restrictions.",
            )
        )

    # 4. First-party or server-side tagging
    ss_name = "First-party or server-side tagging"
    if s["server_side"]:
        detail = ", ".join(s["custom_loader_hosts"]) or "server container configuration present"
        checks.append(_make(ss_name, "pass", 15, f"Detected: {detail}.", "Confirm the server container is monitored and cookies are set first party."))
    else:
        checks.append(
            _make(
                ss_name,
                "fail",
                15,
                "Tags load from third-party domains with no server-side configuration detected.",
                "Evaluate server-side tagging on a first-party subdomain to improve data durability and control.",
            )
        )

    # 5. HTTPS
    if s["https"] is None:
        checks.append(_make("Secure transport", "unverifiable", 5, "No URL supplied.", "Supply the page URL to check transport security."))
    elif s["https"]:
        checks.append(_make("Secure transport", "pass", 5, "Page served over HTTPS.", "No action required."))
    else:
        checks.append(_make("Secure transport", "fail", 5, "Page is not served over HTTPS.", "Serve all pages over HTTPS. Browsers restrict measurement on insecure pages."))

    # 6. Hygiene
    deductions, issues = 0, []
    if s["legacy_ua_ids"]:
        deductions += 5
        issues.append(f"legacy Universal Analytics ID present ({', '.join(s['legacy_ua_ids'])})")
    if len(s["ga4_ids"]) > 1:
        deductions += 5
        issues.append(f"{len(s['ga4_ids'])} distinct GA4 properties referenced")
    if s["has_gtm"] and s["has_gtag_loader"]:
        deductions += 5
        issues.append("both Tag Manager and a direct Google tag are loaded, which can double count")
    hygiene_points = 15 - deductions
    status = "pass" if deductions == 0 else ("partial" if hygiene_points > 0 else "fail")
    checks.append(
        _make(
            "Tag hygiene",
            status,
            15,
            "No duplication or legacy tags detected." if not issues else "Found: " + "; ".join(issues) + ".",
            "Remove retired tags and ensure each event is sent once per property." if issues else "No action required.",
            points=float(hygiene_points),
        )
    )

    score = round(sum(c.points for c in checks), 1)
    return AuditResult(url=url, score=score, grade=_grade(score), checks=checks, signals=s)


# ----------------------------------------------------------------------------
# Fetching with basic protection against server-side request forgery.
# ----------------------------------------------------------------------------

USER_AGENT = "ads-measurement-portfolio-audit/0.1 (+static page source check)"
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3


def _assert_public_host(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve host: {hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError("Only publicly routable hosts can be audited")


def fetch_html(url: str, timeout: int = 10) -> tuple[str, str]:
    """Fetch page source from a public URL. Returns (html, final_url).

    Redirects are followed manually so that every hop is checked. This reduces
    but does not eliminate server-side request forgery risk, for example through
    DNS rebinding, so run this only in an environment without privileged
    network access.
    """
    current = url.strip()
    for _ in range(MAX_REDIRECTS + 1):
        parsed = urlparse(current)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Enter a full http or https URL")
        _assert_public_host(parsed.hostname)

        response = requests.get(
            current,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        try:
            if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("Redirect without a location")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            chunks, total = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > MAX_BYTES:
                    break
                chunks.append(chunk)
            body = b"".join(chunks)
            return body.decode(response.encoding or "utf-8", errors="replace"), current
        finally:
            response.close()
    raise ValueError("Too many redirects")


# ----------------------------------------------------------------------------
# Sample pages so the demo works offline. All identifiers are fictitious.
# ----------------------------------------------------------------------------

SAMPLE_PAGES = {
    "Basic: direct tag only": (
        "https://shop.example.com/",
        """<html><head>
<script async src="https://www.googletagmanager.com/gtag/js?id=UA-1234567-1"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}
gtag('js', new Date()); gtag('config', 'UA-1234567-1');</script>
</head><body>Example store</body></html>""",
    ),
    "Typical: Tag Manager with consent platform": (
        "https://shop.example.com/",
        """<html><head>
<script src="https://consent.cookiebot.com/uc.js" data-cbid="00000000-0000-0000-0000-000000000000"></script>
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});
var f=d.getElementsByTagName(s)[0],j=d.createElement(s);j.async=true;
j.src='https://www.googletagmanager.com/gtm.js?id='+i;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','GTM-TEST123');</script>
</head><body>Example store</body></html>""",
    ),
    "Modern: consent v2, enhanced conversions, server-side": (
        "https://shop.example.com/",
        """<html><head>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}
gtag('consent','default',{ad_storage:'denied',analytics_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',wait_for_update:500});</script>
<script src="https://cdn.cookielaw.org/scripttemplates/otSDKStub.js"></script>
<script async src="https://metrics.example.com/gtag/js?id=G-TEST123456"></script>
<script>gtag('js', new Date());
gtag('config','G-TEST123456',{server_container_url:'https://metrics.example.com'});
gtag('config','AW-123456789',{allow_enhanced_conversions:true});
gtag('set','user_data',{email:'hashed-at-source'});</script>
</head><body>Example store</body></html>""",
    ),
}
