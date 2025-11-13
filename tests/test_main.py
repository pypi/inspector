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


def test_versions(monkeypatch):
    stub_json = {"releases": {"0.5.1e": None}}
    stub_response = pretend.stub(
        status_code=200,
        json=lambda: stub_json,
    )
    get = pretend.call_recorder(lambda a: stub_response)
    monkeypatch.setattr(
        inspector.main, "requests_session", lambda: pretend.stub(get=get)
    )

    render_template = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(inspector.main, "render_template", render_template)

    inspector.main.versions("foo")

    assert get.calls == [pretend.call("https://pypi.org/pypi/foo/json")]
    assert render_template.calls == [
        pretend.call(
            "releases.html",
            releases={"0.5.1e": None},
            h2="foo",
            h2_link="/project/foo",
            h2_paren="View this project on PyPI",
            h2_paren_link="https://pypi.org/project/foo",
        )
    ]
