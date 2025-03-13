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


class Distribution:
    def namelist(self):
        raise NotImplementedError

    def read(self):
        raise NotImplementedError


class ZipDistribution(Distribution):
    def __init__(self, f):
        f.seek(0)
        try:
            self.zipfile = zipfile.ZipFile(f)
        except zipfile.BadZipFile:
            raise BadFileError("Bad zipfile")

    def namelist(self):
        return [i.filename for i in self.zipfile.infolist() if not i.is_dir()]

    def contents(self, filepath) -> bytes:
        try:
            return self.zipfile.read(filepath)
        except KeyError:
            raise FileNotFoundError


class TarGzDistribution(Distribution):
    def __init__(self, f):
        f.seek(0)
        try:
            self.tarfile = tarfile.open(fileobj=f, mode="r:gz")
        except tarfile.BadGzipFile:
            raise BadFileError("Bad gzip file")

    def namelist(self):
        return [i.name for i in self.tarfile.getmembers() if not i.isdir()]

    def contents(self, filepath):
        try:
            file_ = self.tarfile.extractfile(filepath)
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
