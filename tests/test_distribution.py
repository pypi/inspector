import io
import tarfile
import zipfile

import pytest

from inspector.distribution import TarGzDistribution, ZipDistribution


def make_targz(members):
    f = io.BytesIO()
    with tarfile.open(fileobj=f, mode="w:gz") as tf:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    f.seek(0)
    return f


def make_zip(members):
    f = io.BytesIO()
    with zipfile.ZipFile(f, "w") as zf:
        for name, data in members:
            zf.writestr(name, data)
    f.seek(0)
    return f


@pytest.mark.parametrize(
    "make,cls",
    [(make_targz, TarGzDistribution), (make_zip, ZipDistribution)],
)
def test_dot_prefixed_members_are_browsable(make, cls):
    """Members with /./ or ./ prefixes list and resolve under clean names."""
    dist = cls(
        make(
            [
                ("/./pkg-1.0/setup.py", b"setup"),
                ("./pkg-1.0/pkg/__init__.py", b"init"),
                ("pkg-1.0/pkg/./util.py", b"util"),
            ]
        )
    )

    assert dist.namelist() == [
        "pkg-1.0/setup.py",
        "pkg-1.0/pkg/__init__.py",
        "pkg-1.0/pkg/util.py",
    ]
    assert dist.contents("pkg-1.0/setup.py") == b"setup"
    assert dist.contents("pkg-1.0/pkg/__init__.py") == b"init"
    assert dist.contents("pkg-1.0/pkg/util.py") == b"util"


@pytest.mark.parametrize(
    "make,cls",
    [(make_targz, TarGzDistribution), (make_zip, ZipDistribution)],
)
def test_normal_members_unchanged(make, cls):
    dist = cls(make([("pkg-1.0/normal.py", b"normal"), ("README.rst", b"readme")]))

    assert dist.namelist() == ["pkg-1.0/normal.py", "README.rst"]
    assert dist.contents("pkg-1.0/normal.py") == b"normal"
    assert dist.contents("README.rst") == b"readme"
    with pytest.raises(FileNotFoundError):
        dist.contents("pkg-1.0/missing.py")


@pytest.mark.parametrize(
    "make,cls",
    [(make_targz, TarGzDistribution), (make_zip, ZipDistribution)],
)
def test_dotdot_members_cannot_escape_root(make, cls):
    """.. segments are resolved inside the archive, never above its root."""
    dist = cls(
        make(
            [
                ("../evil.py", b"evil"),
                ("pkg-1.0/../../evil2.py", b"evil2"),
                ("pkg-1.0/sub/../ok.py", b"ok"),
            ]
        )
    )

    names = dist.namelist()
    assert all(not name.startswith("..") for name in names)
    assert names == ["evil.py", "evil2.py", "pkg-1.0/ok.py"]
    assert dist.contents("evil.py") == b"evil"
    assert dist.contents("pkg-1.0/ok.py") == b"ok"
    # A request that tries to walk above the root resolves inside it too,
    # and only ever matches archive members -- nothing outside the archive.
    with pytest.raises(FileNotFoundError):
        dist.contents("../../etc/passwd")
