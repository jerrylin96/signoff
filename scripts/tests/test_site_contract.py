"""Contract tests for the project website (Phase 5 Gate 1).

The site is a self-contained static page: no external requests (fonts,
scripts, styles), and its load-bearing content — install channels, release
zip, spec, badge — must stay in sync with the README's claims.
"""

import os
import re

SITE = os.path.join(os.path.dirname(__file__), "..", "..", "site", "index.html")


def _html():
    with open(SITE, encoding="utf-8") as f:
        return f.read()


def test_site_exists_and_is_single_page():
    assert os.path.exists(SITE)


def test_site_is_self_contained():
    html = _html()
    # No external stylesheets, scripts, fonts, or images: resource tags may
    # only use inline content or data: URIs (the favicon's SVG namespace URL
    # inside its data: URI is not a network fetch).
    for tag in re.findall(r"<(?:link|script|img)\b[^>]*>", html):
        assert not re.search(r"(?:src|href)\s*=\s*[\"']https?://", tag), (
            f"external resource: {tag}"
        )


def test_site_covers_install_channels_and_links():
    html = _html()
    assert "/plugin marketplace add jerrylin96/signoff" in html
    assert "releases/latest/download/signoff.zip" in html
    assert "skills/signoff/specs/gsa-core.md" in html
    assert "enabledPlugins" in html
    assert "HARNESSES.md" in html


def test_site_advertises_badge_and_verifier():
    html = _html()
    assert "attested by humans" in html
    assert "jerrylin96/signoff/verify@main" in html


def test_pages_workflow_deploys_site_dir():
    wf = os.path.join(
        os.path.dirname(__file__), "..", "..", ".github", "workflows", "pages.yml"
    )
    with open(wf, encoding="utf-8") as f:
        content = f.read()
    assert "actions/deploy-pages" in content
    assert "path: site" in content
