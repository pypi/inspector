import pretend

import inspector.main


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
