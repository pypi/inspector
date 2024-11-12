import os
import urllib.parse

import gunicorn.http.errors
import requests
import sentry_sdk

from flask import Flask, Response, abort, redirect, render_template, request, url_for
from packaging.utils import canonicalize_name
from sentry_sdk.integrations.flask import FlaskIntegration

from .analysis.checks import basic_details
from .deob import decompile, disassemble
from .distribution import _get_dist
from .legacy import parse
from .utilities import pypi_report_form


def traces_sampler(sampling_context):
    """
    Filter out noisy transactions.
    See https://github.com/getsentry/sentry-python/discussions/1569
    """
    path = sampling_context.get("wsgi_environ", {}).get("PATH_INFO", None)
    if path and path == "/_health/":
        return 0
    return 1


if SENTRY_DSN := os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        traces_sampler=traces_sampler,
    )

app = Flask(__name__)

app.jinja_env.filters["unquote"] = lambda u: urllib.parse.unquote(u)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True


@app.errorhandler(gunicorn.http.errors.ParseException)
def handle_bad_request(e):
    return abort(400)


@app.route("/")
def index():
    if project := request.args.get("project"):
        project = project.strip()
        return redirect(f"/project/{project}")
    return render_template("index.html")


@app.route("/project/<project_name>/")
def versions(project_name):
    if project_name != canonicalize_name(project_name):
        return redirect(
            url_for("versions", project_name=canonicalize_name(project_name)), 301
        )

    resp = requests.get(f"https://pypi.org/pypi/{project_name}/json")
    pypi_project_url = f"https://pypi.org/project/{project_name}"

    # Self-host 404 page to mitigate iframe embeds
    if resp.status_code == 404:
        return render_template("404.html")
    if resp.status_code != 200:
        return redirect(pypi_project_url, 307)

    releases = resp.json()["releases"]
    sorted_releases = {
        version: releases[version]
        for version in sorted(releases.keys(), key=parse, reverse=True)
    }

    return render_template(
        "releases.html",
        releases=sorted_releases,
        h2=project_name,
        h2_link=f"/project/{project_name}",
        h2_paren="View this project on PyPI",
        h2_paren_link=pypi_project_url,
    )


@app.route("/project/<project_name>/<version>/")
def distributions(project_name, version):
    if project_name != canonicalize_name(project_name):
        return redirect(
            url_for(
                "distributions",
                project_name=canonicalize_name(project_name),
                version=version,
            ),
            301,
        )

    resp = requests.get(f"https://pypi.org/pypi/{project_name}/{version}/json")
    if resp.status_code != 200:
        return redirect(f"/project/{project_name}/")

    dist_urls = [
        "." + urllib.parse.urlparse(url["url"]).path + "/"
        for url in resp.json()["urls"]
    ]
    return render_template(
        "links.html",
        links=dist_urls,
        h2=f"{project_name}",
        h2_link=f"/project/{project_name}",
        h2_paren="View this project on PyPI",
        h2_paren_link=f"https://pypi.org/project/{project_name}",
        h3=f"{project_name}=={version}",
        h3_link=f"/project/{project_name}/{version}",
        h3_paren="View this release on PyPI",
        h3_paren_link=f"https://pypi.org/project/{project_name}/{version}",
    )


@app.route(
    "/project/<project_name>/<version>/packages/<first>/<second>/<rest>/<distname>/"
)
def distribution(project_name, version, first, second, rest, distname):
    if project_name != canonicalize_name(project_name):
        return redirect(
            url_for(
                "distribution",
                project_name=canonicalize_name(project_name),
                version=version,
                first=first,
                second=second,
                rest=rest,
                distname=distname,
            ),
            301,
        )

    dist = _get_dist(first, second, rest, distname)

    h2_paren = "View this project on PyPI"
    resp = requests.get(f"https://pypi.org/pypi/{project_name}/json")
    if resp.status_code == 404:
        h2_paren = "❌ Project no longer on PyPI"

    h3_paren = "View this release on PyPI"
    resp = requests.get(f"https://pypi.org/pypi/{project_name}/{version}/json")
    if resp.status_code == 404:
        h3_paren = "❌ Release no longer on PyPI"

    if dist:
        file_urls = [
            "./" + urllib.parse.quote(filename) for filename in dist.namelist()
        ]
        return render_template(
            "links.html",
            links=file_urls,
            h2=f"{project_name}",
            h2_link=f"/project/{project_name}",
            h2_paren=h2_paren,
            h2_paren_link=f"https://pypi.org/project/{project_name}",
            h3=f"{project_name}=={version}",
            h3_link=f"/project/{project_name}/{version}",
            h3_paren=h3_paren,
            h3_paren_link=f"https://pypi.org/project/{project_name}/{version}",
            h4=distname,
            h4_link=f"/project/{project_name}/{version}/packages/{first}/{second}/{rest}/{distname}/",  # noqa
        )
    else:
        return "Distribution type not supported"


@app.route(
    "/project/<project_name>/<version>/packages/<first>/<second>/<rest>/<distname>/<path:filepath>"  # noqa
)
def file(project_name, version, first, second, rest, distname, filepath):
    if project_name != canonicalize_name(project_name):
        return redirect(
            url_for(
                "file",
                project_name=canonicalize_name(project_name),
                version=version,
                first=first,
                second=second,
                rest=rest,
                distname=distname,
                filepath=filepath,
            ),
            301,
        )

    h2_paren = "View this project on PyPI"
    resp = requests.get(f"https://pypi.org/pypi/{project_name}/json")
    if resp.status_code == 404:
        h2_paren = "❌ Project no longer on PyPI"

    h3_paren = "View this release on PyPI"
    resp = requests.get(f"https://pypi.org/pypi/{project_name}/{version}/json")
    if resp.status_code == 404:
        h3_paren = "❌ Release no longer on PyPI"

    dist = _get_dist(first, second, rest, distname)
    if dist:
        try:
            contents = dist.contents(filepath)
        except FileNotFoundError:
            return abort(404)
        file_extension = filepath.split(".")[-1]
        report_link = pypi_report_form(project_name, version, filepath, request.url)

        details = [detail.html() for detail in basic_details(dist, filepath)]
        common_params = {
            "file_details": details,
            "mailto_report_link": report_link,
            "h2": f"{project_name}",
            "h2_link": f"/project/{project_name}",
            "h2_paren": h2_paren,
            "h2_paren_link": f"https://pypi.org/project/{project_name}",
            "h3": f"{project_name}=={version}",
            "h3_link": f"/project/{project_name}/{version}",
            "h3_paren": h3_paren,
            "h3_paren_link": f"https://pypi.org/project/{project_name}/{version}",
            "h4": distname,
            "h4_link": f"/project/{project_name}/{version}/packages/{first}/{second}/{rest}/{distname}/",  # noqa
            "h5": filepath,
            "h5_link": f"/project/{project_name}/{version}/packages/{first}/{second}/{rest}/{distname}/{filepath}",  # noqa
        }

        if file_extension in ["pyc", "pyo"]:
            disassembly = disassemble(contents)
            decompilation = decompile(contents)
            return render_template(
                "disasm.html",
                disassembly=disassembly,
                decompilation=decompilation,
                **common_params,
            )

        if isinstance(contents, bytes):
            try:
                contents = contents.decode()
            except UnicodeDecodeError:
                return "Binary files are not supported."

        return render_template(
            "code.html", code=contents, name=file_extension, **common_params
        )  # noqa
    else:
        return "Distribution type not supported"


@app.route("/_health/")
def health():
    return "OK"


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /", mimetype="text/plain")
