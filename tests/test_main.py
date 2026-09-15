import pretend
import pytest

import inspector.main


@pytest.mark.parametrize(
    "text,encoding",
    [
        # UTF-8 (most common)
        ("Hello, World!", "utf-8"),
        # Windows CP1252 with trademark symbol
        ("Windows™ text", "cp1252"),
        # Shift_JIS - Japanese
        ("こんにちは世界", "shift_jis"),
        # EUC-KR - Korean
        ("안녕하세요", "euc-kr"),
        # Big5 - Traditional Chinese
        ("繁體中文", "big5"),
        # CP1251 - Russian/Cyrillic
        ("Привет мир", "cp1251"),
    ],
)
def test_decode_with_fallback_various_encodings(text, encoding):
    """Test decoding bytes with various text encodings that work correctly.

    These 6 encodings decode correctly with the current ordering and heuristics.
    """
    content = text.encode(encoding)
    result = inspector.main.decode_with_fallback(content)
    assert result == text


@pytest.mark.parametrize(
    "text,encoding,decoded_by",
    [
        ("你好世界", "gbk", "big5 or euc-kr"),
        ("中文测试", "gb2312", "shift_jis (rejected) then euc-kr"),
        ("Héllo Wörld", "iso-8859-1", "big5 (rejected) then cp1251"),
        ("Cześć świat", "iso-8859-2", "big5 (rejected) then cp1251"),
    ],
)
def test_decode_with_fallback_misdetected_encodings(text, encoding, decoded_by):
    """Test encodings that still get misdetected despite improved heuristics.

    These encodings are misdetected by earlier encodings in the `common_encodings` list.
    Improved heuristics help but can't solve all cases without breaking others.

    Tried cross-Asian heuristics that reject some misdetections (e.g., shift_jis
    with excessive half-width katakana, Asian encodings with ASCII+CJK mix),
    but ordering remains a fundamental trade-off:
    no order works perfectly for all encodings.
    """
    content = text.encode(encoding)
    result = inspector.main.decode_with_fallback(content)
    # Should decode to something (not None), but won't match original
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0
    # Verify it's actually different (misdetected)
    assert result != text


@pytest.mark.parametrize(
    "description,binary_data",
    [
        (
            "Random binary with null bytes",
            bytes([0xFF, 0xFE, 0x00, 0x00, 0x01, 0x02, 0x03]),
        ),
        ("Null bytes only", bytes([0x00] * 10)),
        ("Low control characters", bytes([0x01, 0x02, 0x03, 0x04, 0x05])),
        ("JPEG header", bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10])),
    ],
)
def test_decode_with_fallback_binary(description, binary_data):
    """Test that binary data with many control characters returns None.

    Binary data should be rejected by our heuristics even though some
    encodings (like UTF-8 for ASCII control chars, or cp1251 for high bytes)
    can technically decode them.
    """
    result = inspector.main.decode_with_fallback(binary_data)
    assert result is None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(inspector.main.app.config, "TESTING", True)
    return inspector.main.app.test_client()


def _stub_get(responses_by_url):
    """Build a fake ``requests_session().get`` that answers based on the
    requested URL, for routes that make more than one distinct request."""

    def get(url, *a, **kw):
        return responses_by_url[url]

    return get


def _json_resp(status_code, payload=None):
    return pretend.stub(status_code=status_code, json=lambda: payload)


def _patch_requests(monkeypatch, responses_by_url):
    monkeypatch.setattr(
        inspector.main,
        "requests_session",
        lambda: pretend.stub(get=_stub_get(responses_by_url)),
    )


def test_versions_quarantined_json_404_shows_quarantine_page(monkeypatch, client):
    """Original behavior: a quarantined project's legacy JSON API hides it
    entirely (404), so the project page still renders the standalone
    quarantined.html unavailable page in that case."""
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/foo/json": _json_resp(404),
            "https://pypi.org/simple/foo/": _json_resp(
                200, {"project-status": {"status": "quarantined"}}
            ),
        },
    )
    response = client.get("/project/foo/")
    assert b"project-banner--quarantined" in response.data
    assert b"https://pypi.org/project/foo" in response.data
    # The unavailable page has no version listing or installer.
    assert b"data-installer-command" not in response.data


def test_versions_quarantined_with_200_json_still_shows_content(monkeypatch, client):
    """A project can be quarantined per the Simple API while the legacy
    JSON API still answers 200 -- existing retrievable content (the release
    list) must remain visible, with a warning banner and no installer."""
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/foo/json": _json_resp(
                200, {"releases": {"1.0": [{"upload_time": "2020-01-01"}]}}
            ),
            "https://pypi.org/simple/foo/": _json_resp(
                200, {"project-status": {"status": "quarantined"}}
            ),
        },
    )
    response = client.get("/project/foo/")
    assert response.status_code == 200
    assert b"project-banner--quarantined" in response.data
    assert b"1.0" in response.data  # release list still retrievable
    assert b"data-installer-command" not in response.data  # installer suppressed


def test_versions_archived_shows_banner_but_keeps_installer(monkeypatch, client):
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/foo/json": _json_resp(
                200, {"releases": {"1.0": [{"upload_time": "2020-01-01"}]}}
            ),
            "https://pypi.org/simple/foo/": _json_resp(
                200, {"project-status": {"status": "archived"}}
            ),
        },
    )
    response = client.get("/project/foo/")
    assert b"project-banner--archived" in response.data
    assert b"data-installer-command" in response.data


@pytest.mark.parametrize(
    "project_status,info,expected_banner_class",
    [
        # Uncertain precedence: yanked wins over archived for the latest
        # release, even though the project itself is archived.
        (
            "archived",
            {"version": "2.0", "yanked": True, "yanked_reason": "bad release"},
            b"project-banner--yanked",
        ),
        # Quarantine always wins, even alongside a yanked latest release.
        (
            "quarantined",
            {"version": "2.0", "yanked": True, "yanked_reason": "bad release"},
            b"project-banner--quarantined",
        ),
        # Archived wins over a merely-prerelease latest version.
        (
            "archived",
            {"version": "2.0a1", "yanked": False},
            b"project-banner--archived",
        ),
    ],
)
def test_versions_banner_precedence(
    monkeypatch, client, project_status, info, expected_banner_class
):
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/foo/json": _json_resp(
                200,
                {
                    "releases": {info["version"]: [{"upload_time": "2020-01-01"}]},
                    "info": info,
                },
            ),
            "https://pypi.org/simple/foo/": _json_resp(
                200, {"project-status": {"status": project_status}}
            ),
        },
    )
    response = client.get("/project/foo/")
    assert expected_banner_class in response.data


def test_distributions_release_not_found_redirects(monkeypatch, client):
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/foo/1.0/json": _json_resp(404),
            "https://pypi.org/simple/foo/": _json_resp(200, {}),
        },
    )
    response = client.get("/project/foo/1.0/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/project/foo/"


def test_distributions_yanked_release_shows_reason(monkeypatch, client):
    """A release-level yank (info.yanked) is authoritative and surfaces the
    real reason -- mirrors anyio 4.6.2's mistagged-release yank."""
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/anyio/4.6.2/json": _json_resp(
                200,
                {
                    "info": {
                        "yanked": True,
                        "yanked_reason": "This was 4.5.2 code, mistagged",
                    },
                    "urls": [],
                    "vulnerabilities": [],
                },
            ),
            "https://pypi.org/simple/anyio/": _json_resp(200, {}),
        },
    )
    response = client.get("/project/anyio/4.6.2/")
    assert b"project-banner--yanked" in response.data
    assert b"This was 4.5.2 code, mistagged" in response.data


def test_distributions_single_yanked_file_does_not_yank_whole_release(
    monkeypatch, client
):
    """A single yanked file within an otherwise-live release must not be
    reported as the whole release being yanked when ``info`` lacks the
    yanked fields (malformed/legacy data) -- avoid the one-file-taints-all
    bug."""
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/foo/1.0/json": _json_resp(
                200,
                {
                    "info": {},
                    "urls": [
                        {
                            "filename": "foo-1.0-py3-none-any.whl",
                            "url": "https://files.pythonhosted.org/foo.whl",
                            "yanked": True,
                            "yanked_reason": "bad wheel build",
                        },
                        {
                            "filename": "foo-1.0.tar.gz",
                            "url": "https://files.pythonhosted.org/foo.tar.gz",
                            "yanked": False,
                            "yanked_reason": None,
                        },
                    ],
                    "vulnerabilities": [],
                },
            ),
            "https://pypi.org/simple/foo/": _json_resp(200, {}),
        },
    )
    response = client.get("/project/foo/1.0/")
    assert b"project-banner--yanked" not in response.data
    assert b"data-installer-command" in response.data


def test_distributions_all_files_yanked_falls_back_to_release_yank(monkeypatch, client):
    """When every file for a release was yanked but ``info`` lacks the
    yanked fields, the release is still treated as yanked."""
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/foo/1.0/json": _json_resp(
                200,
                {
                    "info": {},
                    "urls": [
                        {
                            "filename": "foo-1.0-py3-none-any.whl",
                            "url": "https://files.pythonhosted.org/foo.whl",
                            "yanked": True,
                            "yanked_reason": "bad build",
                        },
                        {
                            "filename": "foo-1.0.tar.gz",
                            "url": "https://files.pythonhosted.org/foo.tar.gz",
                            "yanked": True,
                            "yanked_reason": None,
                        },
                    ],
                    "vulnerabilities": [],
                },
            ),
            "https://pypi.org/simple/foo/": _json_resp(200, {}),
        },
    )
    response = client.get("/project/foo/1.0/")
    assert b"project-banner--yanked" in response.data
    assert b"bad build" in response.data


def test_distributions_quarantined_still_shows_files_suppresses_installer(
    monkeypatch, client
):
    """Quarantine is a UI status, not an access gate: retrievable release
    content stays visible with a warning, but the installer is suppressed."""
    _patch_requests(
        monkeypatch,
        {
            "https://pypi.org/pypi/foo/1.0/json": _json_resp(
                200,
                {
                    "info": {},
                    "urls": [
                        {
                            "filename": "foo-1.0.tar.gz",
                            "url": "https://files.pythonhosted.org/foo.tar.gz",
                            "yanked": False,
                            "yanked_reason": None,
                        }
                    ],
                    "vulnerabilities": [],
                },
            ),
            "https://pypi.org/simple/foo/": _json_resp(
                200, {"project-status": {"status": "quarantined"}}
            ),
        },
    )
    response = client.get("/project/foo/1.0/")
    assert response.status_code == 200
    assert b"project-banner--quarantined" in response.data
    assert b"foo-1.0.tar.gz" in response.data  # file listing still retrievable
    assert b"data-installer-command" not in response.data
    assert b"https://pypi.org/project/foo" in response.data  # "View on PyPI" link
