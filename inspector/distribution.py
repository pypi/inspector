import tarfile

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


class GemDistribution(Distribution):
    def __init__(self, f):
        f.seek(0)
        self.tarfile = tarfile.open(fileobj=f, mode="r")

    def unpack_name(self, entry):
        if entry.name.endswith(".tar.gz"):
            return [
                "/".join([entry.name, i.name])
                for i in tarfile.open(
                    fileobj=self.tarfile.extractfile(entry), mode="r"
                ).getmembers()
            ]
        return [entry.name]

    def namelist(self):
        list = []
        for i in self.tarfile.getmembers():
            list.extend(self.unpack_name(i))
        return list

    def _read_data(self, filepath):
        try:
            file = tarfile.open(
                fileobj=self.tarfile.extractfile("data.tar.gz"), mode="r"
            ).extractfile(filepath)
            if file:
                return file.read()
            else:
                raise FileNotFoundError
        except (KeyError, EOFError):
            raise FileNotFoundError

    def contents(self, filepath):
        if filepath.startswith("data.tar.gz"):
            return self._read_data(filepath.removeprefix("data.tar.gz/"))

        try:
            file_ = self.tarfile.extractfile(filepath)
            if file_:
                return file_.read()
            else:
                raise FileNotFoundError
        except (KeyError, EOFError):
            raise FileNotFoundError


def _get_dist(project_name, version, platform):
    full_name = (
        f"{project_name}-{version}.gem"
        if platform == "ruby"
        else f"{project_name}-{version}-{platform}.gem"
    )
    if full_name in dists:
        return dists[full_name]

    url = f"https://index.rubygems.org/gems/{full_name}"
    try:
        resp = requests_session().get(url, stream=True)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        abort(exc.response.status_code)

    f = BytesIO(resp.content)

    distfile = GemDistribution(f)
    dists[full_name] = distfile
    return distfile
