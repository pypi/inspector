import pretend

import inspector.main


def test_versions(monkeypatch):
    stub_json = [
        {"number": "1.0", "platform": "ruby"},
        {"number": "1.0", "platform": "java"},
        {"number": "2.0", "platform": "ruby"},
    ]
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

    assert get.calls == [pretend.call("https://rubygems.org/api/v1/versions/foo.json")]
    assert render_template.calls == [
        pretend.call(
            "releases.html",
            releases={
                "1.0": [
                    {"number": "1.0", "platform": "ruby"},
                    {"number": "1.0", "platform": "java"},
                ],
                "2.0": [{"number": "2.0", "platform": "ruby"}],
            },
            h2="foo",
            h2_link="/gems/foo",
            h2_paren="View this project on RubyGems.org",
            h2_paren_link="https://rubygems.org/gems/foo",
        )
    ]
