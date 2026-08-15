import os
import urllib.parse

import gunicorn.http.errors
import sentry_sdk

from flask import Flask, Response, abort, redirect, render_template, request, url_for
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from sentry_sdk.integrations.flask import FlaskIntegration

from .analysis.checks import basic_details
from .deob import decompile, disassemble
from .distribution import _get_dist
from .errors import InspectorError
from .legacy import parse
from .utilities import pypi_report_form, requests_session


PACKAGE_TYPE_LABELS = {
    "bdist_wheel": "Wheel",
    "sdist": "Source",
    "bdist_egg": "Egg",
    "bdist_msi": "MSI",
    "bdist_rpm": "RPM",
    "bdist_dmg": "DMG",
    "bdist_wininst": "Windows Installer",
}


def _human_size(num_bytes):
    """Render a byte count as a short human-readable string, e.g. '12.3 KB'."""
    if num_bytes is None:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _parse_classifiers(classifiers):
    """Pull a development-status label and supported Python versions out of
    PyPI's classifier strings, e.g. 'Development Status :: 5 - Production/Stable'
    and 'Programming Language :: Python :: 3.11'."""
    development_status = None
    python_versions = []
    for classifier in classifiers:
        if classifier.startswith("Development Status :: "):
            development_status = classifier.split(" :: ", 1)[1]
        elif classifier.startswith("Programming Language :: Python :: "):
            version = classifier.rsplit(" :: ", 1)[-1]
            if "." in version and version[0].isdigit():
                python_versions.append(version)
    return development_status, sorted(python_versions, key=parse)


def _parse_dependency(raw):
    """Turn a requires_dist entry into a display string plus a link to that
    dependency's own inspector page, when the name is parseable."""
    try:
        name = Requirement(raw).name
    except InvalidRequirement:
        return {"raw": raw, "name": None}
    return {"raw": raw, "name": canonicalize_name(name)}


def _is_likely_text(decoded_str):
    """Check if decoded string looks like valid text (not corrupted)."""
    if not decoded_str:
        return True

    # Too many control characters suggests wrong encoding
    control_chars = sum(1 for c in decoded_str if ord(c) < 32 and c not in "\t\n\r")
    return control_chars / len(decoded_str) <= 0.3


def _is_likely_misencoded_asian_text(decoded_str, encoding):
    """
    Detect when Western encodings decode Asian text as Latin Extended garbage.

    When cp1252/latin-1 decode multi-byte Asian text, they produce strings
    with many Latin Extended/Supplement characters and few/no spaces.
    """
    if encoding not in ("cp1252", "latin-1") or len(decoded_str) <= 3:
        return False

    # Count Latin Extended-A/B (Ā-ʯ) and Latin-1 Supplement (À-ÿ)
    high_latin = sum(1 for c in decoded_str if 0x0080 <= ord(c) <= 0x024F)
    spaces = decoded_str.count(" ")

    # If >50% high Latin chars and <10% spaces, likely misencoded
    return high_latin / len(decoded_str) > 0.5 and spaces < len(decoded_str) * 0.1


def _is_likely_misencoded_cross_asian(decoded_str, encoding):
    """
    Detect when Asian encodings misinterpret other Asian encodings.

    Patterns:
    - shift_jis decoding GB2312 produces excessive half-width katakana
    - Asian encodings decoding Western text produce ASCII+CJK mix (unlikely)
    """
    if len(decoded_str) <= 3:
        return False

    # Pattern 1: Excessive half-width katakana (shift_jis misinterpreting GB2312)
    # Half-width katakana range: U+FF61-FF9F
    if encoding == "shift_jis":
        half_width_katakana = sum(1 for c in decoded_str if 0xFF61 <= ord(c) <= 0xFF9F)
        # If >30% is half-width katakana, likely wrong encoding
        # (Real Japanese text uses mostly full-width kana and kanji)
        if half_width_katakana / len(decoded_str) > 0.3:
            return True

    # Pattern 2: ASCII mixed with CJK (Asian encoding misinterpreting Western)
    # CJK Unified Ideographs: U+4E00-U+9FFF
    if encoding in ("big5", "gbk", "gb2312", "shift_jis", "euc-kr"):
        ascii_chars = sum(1 for c in decoded_str if ord(c) < 128)
        cjk_chars = sum(1 for c in decoded_str if 0x4E00 <= ord(c) <= 0x9FFF)

        # If we have ASCII letters and scattered CJK chars, likely misencoded
        # Real CJK text is mostly CJK with occasional ASCII punctuation
        if ascii_chars > 0 and cjk_chars > 0:
            # Check if there are ASCII letters (not just punctuation)
            ascii_letters = sum(1 for c in decoded_str if c.isalpha() and ord(c) < 128)
            # If we have ASCII letters AND CJK, and CJK is <50%, likely wrong
            if ascii_letters >= 2 and cjk_chars / len(decoded_str) < 0.5:
                return True

    return False


def decode_with_fallback(content_bytes):
    """
    Decode bytes to string, trying multiple encodings.

    Strategy:
    1. Try UTF-8 (most common)
    2. Try common encodings with sanity checks
    3. Fall back to latin-1 (decodes anything, but may produce garbage)

    Returns decoded string or None if all attempts fail (only if truly binary).
    """
    # Try UTF-8 first (most common)
    try:
        decoded = content_bytes.decode("utf-8")
        # Apply same heuristics as other encodings
        if _is_likely_text(decoded):
            return decoded
    except (UnicodeDecodeError, AttributeError):
        pass

    # Try encodings from most to least restrictive. Even with improved heuristics,
    # putting GBK/GB2312 early breaks too many other encodings. The order below
    # maximizes correct detections while minimizing misdetections.
    common_encodings = [
        "shift_jis",  # Japanese (restrictive multi-byte)
        "euc-kr",  # Korean (restrictive multi-byte)
        "big5",  # Chinese Traditional (restrictive multi-byte)
        "gbk",  # Chinese Simplified
        "gb2312",  # Chinese Simplified, older
        "cp1251",  # Cyrillic
        "iso-8859-2",  # Central/Eastern European
        "cp1252",  # Windows Western European (very permissive)
        "latin-1",  # ISO-8859-1 fallback (never fails)
    ]

    for encoding in common_encodings:
        try:
            decoded = content_bytes.decode(encoding)

            # Skip if decoded text looks corrupted
            if not _is_likely_text(decoded):
                continue

            # Skip if Western encoding produced Asian-text-as-garbage pattern
            if _is_likely_misencoded_asian_text(decoded, encoding):
                continue

            # Skip if Asian encoding misinterpreted other Asian/Western text
            if _is_likely_misencoded_cross_asian(decoded, encoding):
                continue

            return decoded

        except (UnicodeDecodeError, LookupError):
            continue

    # If we get here, all encodings failed sanity checks (truly binary data)
    return None


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
app.jinja_env.filters["filesizeformat"] = _human_size
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

    resp = requests_session().get(f"https://pypi.org/pypi/{project_name}/json")
    pypi_project_url = f"https://pypi.org/project/{project_name}"

    # Self-host 404 page to mitigate iframe embeds
    if resp.status_code == 404:
        return render_template("404.html")
    if resp.status_code != 200:
        return redirect(pypi_project_url, 307)

    data = resp.json()
    releases = data["releases"]
    sorted_releases = {
        version: releases[version]
        for version in sorted(releases.keys(), key=parse, reverse=True)
    }

    info = data.get("info") or {}
    project_links = dict(info.get("project_urls") or {})
    if info.get("home_page") and "Homepage" not in project_links:
        project_links["Homepage"] = info["home_page"]

    development_status, python_versions = _parse_classifiers(
        info.get("classifiers") or []
    )

    release_status = {}
    for version, files in sorted_releases.items():
        yanked_reason = next(
            (f["yanked_reason"] for f in files if f.get("yanked")), None
        )
        release_status[version] = {
            "yanked": any(f.get("yanked") for f in files),
            "yanked_reason": yanked_reason,
            "prerelease": parse(version).is_prerelease,
        }

    return render_template(
        "releases.html",
        releases=sorted_releases,
        release_status=release_status,
        latest_version=info.get("version"),
        summary=info.get("summary"),
        author=info.get("author") or info.get("maintainer"),
        license=info.get("license"),
        project_links=project_links,
        vulnerabilities=data.get("vulnerabilities") or [],
        requires_python=info.get("requires_python"),
        development_status=development_status,
        python_versions=python_versions,
        dependencies=[
            _parse_dependency(r)
            for r in (info.get("requires_dist") or [])
            if "extra ==" not in r
        ],
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

    resp = requests_session().get(
        f"https://pypi.org/pypi/{project_name}/{version}/json"
    )
    if resp.status_code != 200:
        return redirect(f"/project/{project_name}/")

    version_data = resp.json()
    files = [
        {
            "path": "." + urllib.parse.urlparse(url["url"]).path + "/",
            "filename": url.get("filename"),
            "size": url.get("size"),
            "upload_time": url.get("upload_time"),
            "python_version": url.get("python_version"),
            "packagetype": PACKAGE_TYPE_LABELS.get(
                url.get("packagetype"), url.get("packagetype")
            ),
            "requires_python": url.get("requires_python"),
            "sha256": (url.get("digests") or {}).get("sha256"),
            "yanked": url.get("yanked"),
            "yanked_reason": url.get("yanked_reason"),
        }
        for url in version_data["urls"]
    ]
    return render_template(
        "links.html",
        files=files,
        vulnerabilities=version_data.get("vulnerabilities") or [],
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

    try:
        dist = _get_dist(first, second, rest, distname)
    except InspectorError:
        return abort(400)

    h2_paren = "View this project on PyPI"
    resp = requests_session().get(f"https://pypi.org/pypi/{project_name}/json")
    if resp.status_code == 404:
        h2_paren = "Project no longer on PyPI"

    h3_paren = "View this release on PyPI"
    resp = requests_session().get(
        f"https://pypi.org/pypi/{project_name}/{version}/json"
    )
    if resp.status_code == 404:
        h3_paren = "Release no longer on PyPI"

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
    resp = requests_session().get(f"https://pypi.org/pypi/{project_name}/json")
    if resp.status_code == 404:
        h2_paren = "Project no longer on PyPI"

    h3_paren = "View this release on PyPI"
    resp = requests_session().get(
        f"https://pypi.org/pypi/{project_name}/{version}/json"
    )
    if resp.status_code == 404:
        h3_paren = "Release no longer on PyPI"

    dist = _get_dist(first, second, rest, distname)
    if dist:
        try:
            contents = dist.contents(filepath)
        except FileNotFoundError:
            return abort(404)
        except InspectorError:
            return abort(400)
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
            decoded_contents = decode_with_fallback(contents)
            if decoded_contents is None:
                return "Binary files are not supported."
            contents = decoded_contents

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
