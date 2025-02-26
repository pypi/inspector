import gzip
import itertools
import os
import urllib.parse

import gunicorn.http.errors
import sentry_sdk

from flask import Flask, Response, abort, redirect, render_template, request, url_for
from packaging.utils import canonicalize_name
from sentry_sdk.integrations.flask import FlaskIntegration

from .analysis.checks import basic_details
from .distribution import _get_dist
from .utilities import mailto_report_link, requests_session


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
    if project := request.args.get("gem"):
        project = project.strip()
        return redirect(f"/gems/{project}")
    return render_template("index.html")


@app.route("/gems/<project_name>/")
def versions(project_name):
    if project_name != canonicalize_name(project_name):
        return redirect(
            url_for("versions", project_name=canonicalize_name(project_name)), 301
        )

    resp = requests_session().get(
        f"https://rubygems.org/api/v1/versions/{project_name}.json"
    )
    rubygems_url = f"https://rubygems.org/gems/{project_name}"

    # Self-host 404 page to mitigate iframe embeds
    if resp.status_code == 404:
        return render_template("404.html")
    if resp.status_code != 200:
        return redirect(rubygems_url, 307)

    releases = resp.json()
    by_number = itertools.groupby(releases, lambda x: x["number"])
    sorted_releases = {number: list(versions) for (number, versions) in by_number}

    return render_template(
        "releases.html",
        releases=sorted_releases,
        h2=project_name,
        h2_link=f"/gems/{project_name}",
        h2_paren="View this project on RubyGems.org",
        h2_paren_link=rubygems_url,
    )


def full_name(version):
    if version["platform"] == "ruby":
        return version["number"]
    return f"{version['number']}-{version['platform']}"


@app.route("/gems/<project_name>/<version>/")
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

    resp = requests_session().get(
        f"https://rubygems.org/api/v1/versions/{project_name}.json"
    )
    if resp.status_code != 200:
        return redirect(f"/gems/{project_name}/")

    dist_urls = [f"{v['platform']}" for v in resp.json() if v["number"] == version]
    return render_template(
        "links.html",
        links=dist_urls,
        h2=f"{project_name}",
        h2_link=f"/gems/{project_name}",
        h2_paren="View this project on RubyGems.org",
        h2_paren_link=f"https://rubygems.org/gems/{project_name}",
        h3=f"{project_name}=={version}",
        h3_link=f"/gems/{project_name}/{version}",
        h3_paren="View this release on RubyGems.org",
        h3_paren_link=f"https://rubygems.org/gems/{project_name}/versions/{version}",
    )


@app.route("/gems/<project_name>/<version>/<platform>/")
def distribution(project_name, version, platform):
    if project_name != canonicalize_name(project_name):
        return redirect(
            url_for(
                "distribution",
                project_name=canonicalize_name(project_name),
                version=version,
                platform=platform,
            ),
            301,
        )

    dist = _get_dist(project_name, version, platform)

    h2_paren = "View this project on RubyGems.org"
    resp = requests_session().get(
        f"https://rubygems.org/api/v1/gems/{project_name}.json"
    )
    if resp.status_code == 404:
        h2_paren = "❌ Project no longer on RubyGems.org"

    full_name = version if platform == "ruby" else f"{version}-{platform}"
    h3_paren = "View this release on RubyGems.org"
    resp = requests_session().get(
        f"https://rubygems.org/api/v2/rubygems/{project_name}/versions/{full_name}.json"
    )
    if resp.status_code == 404:
        h3_paren = "❌ Release no longer on RubyGems.org"

    if dist:
        file_urls = [urllib.parse.quote(filename) for filename in dist.namelist()]
        return render_template(
            "links.html",
            links=file_urls,
            h2=f"{project_name}",
            h2_link=f"/gems/{project_name}",
            h2_paren=h2_paren,
            h2_paren_link=f"https://rubygems.org/gems/{project_name}",
            h3=f"{project_name}=={version}",
            h3_link=f"/gems/{project_name}/{version}",
            h3_paren=h3_paren,
            h3_paren_link=f"https://rubygems.org/gems/{project_name}/versions/{version}",
            h4=full_name,
            h4_link=f"/gems/{project_name}/{version}/{platform}",  # noqa
        )
    else:
        return "Distribution type not supported"


@app.route("/gems/<project_name>/<version>/<platform>/<path:filepath>")  # noqa
def file(project_name, version, platform, filepath):
    if project_name != canonicalize_name(project_name):
        return redirect(
            url_for(
                "file",
                project_name=canonicalize_name(project_name),
                version=version,
                platform=platform,
                filepath=filepath,
            ),
            301,
        )

    h2_paren = "View this project on RubyGems.org"
    resp = requests_session().get(
        f"https://rubygems.org/api/v1/gems/{project_name}.json"
    )
    if resp.status_code == 404:
        h2_paren = "❌ Project no longer on RubyGems.org"

    full_name = version if platform == "ruby" else f"{version}-{platform}"
    h3_paren = "View this release on RubyGems.org"
    resp = requests_session().get(
        f"https://rubygems.org/api/v2/rubygems/{project_name}/versions/{full_name}.json"
    )
    if resp.status_code == 404:
        h3_paren = "❌ Release no longer on RubyGems.org"

    dist = _get_dist(project_name, version, platform)
    if dist:
        try:
            contents = dist.contents(filepath)
        except FileNotFoundError:
            return abort(404)
        file_extension = filepath.split(".")[-1]
        report_link = mailto_report_link(
            project_name, version, platform, filepath, request.url
        )

        details = [detail.html() for detail in basic_details(dist, filepath)]
        common_params = {
            "file_details": details,
            "mailto_report_link": report_link,
            "h2": f"{project_name}",
            "h2_link": f"/gems/{project_name}",
            "h2_paren": h2_paren,
            "h2_paren_link": f"https://rubygems.org/gems/{project_name}",
            "h3": f"{project_name}=={version}",
            "h3_link": f"/gems/{project_name}/{version}",
            "h3_paren": h3_paren,
            "h3_paren_link": f"https://rubygems.org/gems/{project_name}/versions/{version}",
            "h4": full_name,
            "h4_link": f"/gems/{project_name}/{version}/{platform}/",  # noqa
            "h5": filepath,
            "h5_link": f"/gems/{project_name}/{version}/{platform}/{filepath}",  # noqa
        }

        if isinstance(contents, bytes):
            if filepath.endswith(".gz"):
                try:
                    contents = gzip.decompress(contents)
                    file_extension = filepath.split(".")[-2]
                    if filepath == "metadata.gz":
                        file_extension = "yaml"
                except gzip.BadGzipFile:
                    return "Failed to ungzip."

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
