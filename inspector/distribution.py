import tarfile
import zipfile

from io import BytesIO

import requests

from flask import abort

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
        self.zipfile = zipfile.ZipFile(f)

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
        self.tarfile = tarfile.open(fileobj=f, mode="r:gz")

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
