import os

from flask import Flask, render_template, redirect, request, abort
import requests
import urllib.parse
from io import BytesIO
import zipfile


app = Flask(__name__)

# Lightweight datastore ;)
dists = {}


@app.route("/")
def index():
    if project := request.args.get("project"):
        return redirect(f"/project/{ project }")
    return render_template("index.html")


@app.route("/project/<project_name>/")
def versions(project_name):
    resp = requests.get(f"https://pypi.org/pypi/{project_name}/json")
    if resp.status_code != 200:
        return abort(404)

    version_urls = ["." + "/" + version for version in resp.json()["releases"].keys()]
    return render_template("links.html", links=version_urls, h2=project_name)


@app.route("/project/<project_name>/<version>/")
def distributions(project_name, version):
    resp = requests.get(f"https://pypi.org/pypi/{project_name}/{version}/json")
    if resp.status_code != 200:
        return abort(404)

    dist_urls = [
        "." + urllib.parse.urlparse(release["url"]).path + "/"
        for release in resp.json()["releases"][version]
    ]
    return render_template(
        "links.html", links=dist_urls, h2=f"{project_name}=={version}"
    )


def _get_dist(first, second, rest, distname):
    if distname in dists:
        return dists[distname]
    url = f"https://files.pythonhosted.org/packages/{first}/{second}/{rest}/{distname}"
    resp = requests.get(url)
    f = BytesIO()
    f.write(resp.content)
    input_zip = zipfile.ZipFile(f)
    dists[distname] = input_zip
    return input_zip


@app.route(
    "/project/<project_name>/<version>/packages/<first>/<second>/<rest>/<distname>/"
)
def distribution(project_name, version, first, second, rest, distname):
    input_zip = _get_dist(first, second, rest, distname)
    file_urls = ["./" + filename for filename in input_zip.namelist()]

    return render_template(
        "links.html",
        links=file_urls,
        h2=f"{project_name}=={version}",
        h3=distname,
    )


@app.route(
    "/project/<project_name>/<version>/packages/<first>/<second>/<rest>/<distname>/<path:filepath>"
)
def file(project_name, version, first, second, rest, distname, filepath):
    input_zip = _get_dist(first, second, rest, distname)
    return render_template(
        "code.html",
        code=input_zip.read(filepath).decode(),
        h2=f"{project_name}=={version}",
        h3=distname,
        h4=filepath,
    )


@app.route("/_health/")
def health():
    return "OK"
