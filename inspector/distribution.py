import gzip
import tarfile
import zipfile
import zlib

from io import BytesIO

import requests

from flask import abort

from .errors import BadFileError
from .utilities import requests_session

# Lightweight datastore ;)
dists = {}


def _normalize_name(name):
    """
    Reduce an archive member name to a canonical, root-relative path.

    Some old distributions were built with member names that carry a
    leading "/./" or "./", or "." segments in the middle of the path.
    Those names can never be addressed over HTTP: URL handling removes
    dot segments, so a request for the file arrives under its normalized
    path and an exact-name lookup against the raw member name misses.

    "." and empty segments are dropped, and ".." segments are resolved
    against the segments seen so far, clamped at the archive root so the
    result can never point outside the distribution.
    """
    parts = []
    for part in name.split("/"):
        if part in ("", "."):
            continue
        elif part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


class Distribution:
    def namelist(self):
        raise NotImplementedError

    def read(self):
        raise NotImplementedError

    def _member_map(self, names):
        """
        Map normalized member names to their original archive names.

        If two members normalize to the same name, the first one in
        archive order wins.
        """
        mapping = {}
        for name in names:
            normalized = _normalize_name(name)
            if normalized and normalized not in mapping:
                mapping[normalized] = name
        return mapping


class ZipDistribution(Distribution):
    def __init__(self, f):
        f.seek(0)
        try:
            self.zipfile = zipfile.ZipFile(f)
        except zipfile.BadZipFile:
            raise BadFileError("Bad zipfile")
        self._members = self._member_map(
            i.filename for i in self.zipfile.infolist() if not i.is_dir()
        )

    def namelist(self):
        return list(self._members)

    def contents(self, filepath) -> bytes:
        try:
            original = self._members[_normalize_name(filepath)]
        except KeyError:
            raise FileNotFoundError
        try:
            return self.zipfile.read(original)
        except KeyError:
            raise FileNotFoundError


class TarGzDistribution(Distribution):
    def __init__(self, f):
        f.seek(0)
        try:
            self.tarfile = tarfile.open(fileobj=f, mode="r:gz")
        except gzip.BadGzipFile:
            raise BadFileError("Bad gzip file")
        self._members = self._member_map(
            i.name for i in self.tarfile.getmembers() if not i.isdir()
        )

    def namelist(self):
        return list(self._members)

    def contents(self, filepath):
        try:
            original = self._members[_normalize_name(filepath)]
        except KeyError:
            raise FileNotFoundError
        try:
            file_ = self.tarfile.extractfile(original)
            if file_:
                return file_.read()
            else:
                raise FileNotFoundError
        except (KeyError, EOFError):
            raise FileNotFoundError
        except (tarfile.TarError, zlib.error):
            raise BadFileError("Bad tarfile")


def _get_dist(first, second, rest, distname):
    if distname in dists:
        return dists[distname]

    url = f"https://files.pythonhosted.org/packages/{first}/{second}/{rest}/{distname}"
    try:
        resp = requests_session().get(url, stream=True)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        abort(exc.response.status_code)

    f = BytesIO(resp.content)

    if (
        distname.endswith(".whl")
        or distname.endswith(".zip")
        or distname.endswith(".egg")
    ):
        distfile = ZipDistribution(f)
        dists[distname] = distfile
        return distfile

    elif distname.endswith(".tar.gz"):
        distfile = TarGzDistribution(f)
        dists[distname] = distfile
        return distfile

    else:
        # Not supported
        return None
