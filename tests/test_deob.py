import platform
import py_compile
import shutil
import subprocess
import sys
import time

from pathlib import Path

import pretend
import pytest

import inspector.deob

from inspector.deob import decompile, disassemble

FIXTURES = Path(__file__).parent / "fixtures"


def test_disassemble_python_3_14():
    disassembly = disassemble((FIXTURES / "greet-3.14.pyc").read_bytes())

    assert "Python bytecode 3.14" in disassembly
    assert "greet" in disassembly
    assert "Unknown magic" not in disassembly
    assert platform.python_version() not in disassembly


@pytest.mark.skipif(shutil.which("pycdc") is None, reason="pycdc is built in Docker")
def test_decompile_runs_pycdc():
    decompilation = decompile((FIXTURES / "greet-3.11.pyc").read_bytes())

    assert "def greet(name):" in decompilation


@pytest.mark.xfail(
    sys.version_info >= (3, 15),
    strict=True,
    reason="xdis 6.3.0 predates the Python 3.15 final magic number",
)
def test_disassemble_running_python(tmp_path):
    pyc = tmp_path / "test_deob.pyc"
    py_compile.compile(
        str(FIXTURES.parent / "test_deob.py"), cfile=str(pyc), doraise=True
    )

    disassembly = disassemble(pyc.read_bytes())

    assert "Unknown magic" not in disassembly
    assert "test_disassemble_running_python" in disassembly


def fake_run(output):
    def run(args, **kwargs):
        kwargs["stdout"].write(output)
        return pretend.stub(returncode=0)

    return run


@pytest.mark.parametrize("func", [decompile, disassemble])
def test_tool_output_not_utf8(monkeypatch, func):
    monkeypatch.setattr(subprocess, "run", fake_run(b"x = 'caf\xed\xb3\xbf'\n"))

    assert "x = 'caf\\xed\\xb3\\xbf'" in func(b"bytecode")


@pytest.mark.parametrize("func", [decompile, disassemble])
def test_tool_timeout(monkeypatch, func):
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", run)

    assert "timed out" in func(b"bytecode")


@pytest.mark.parametrize("func", [decompile, disassemble])
def test_tool_timeout_keeps_partial_output(monkeypatch, func):
    def run(args, **kwargs):
        kwargs["stdout"].write(b"def greet(name):\n")
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", run)

    output = func(b"bytecode")

    assert "def greet(name):" in output
    assert "timed out" in output


@pytest.mark.parametrize("func", [decompile, disassemble])
def test_tool_exit_status(monkeypatch, func):
    def run(args, **kwargs):
        return pretend.stub(returncode=-11)

    monkeypatch.setattr(subprocess, "run", run)

    assert "exited with status -11" in func(b"bytecode")


@pytest.mark.parametrize("func", [decompile, disassemble])
def test_tool_missing(monkeypatch, func):
    def run(args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", args[0])

    monkeypatch.setattr(subprocess, "run", run)

    assert "could not run: No such file or directory" in func(b"bytecode")


@pytest.mark.parametrize("func", [decompile, disassemble])
def test_tool_error_without_strerror(monkeypatch, func):
    def run(args, **kwargs):
        raise PermissionError("not allowed")

    monkeypatch.setattr(subprocess, "run", run)

    assert "could not run: not allowed" in func(b"bytecode")


@pytest.mark.parametrize("func", [decompile, disassemble])
def test_tool_runs_on_relative_path(monkeypatch, func):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs["cwd"]))
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert Path(kwargs["cwd"], args[-1]).read_bytes() == b"bytecode"
        return pretend.stub(returncode=0)

    monkeypatch.setattr(subprocess, "run", run)

    func(b"bytecode")

    [(args, cwd)] = calls
    assert args[-1] == "file.pyc"
    assert not Path(cwd).exists()


@pytest.mark.parametrize("func", [decompile, disassemble])
def test_tool_output_truncated(monkeypatch, func):
    monkeypatch.setattr(inspector.deob, "MAX_OUTPUT", 10)
    monkeypatch.setattr(subprocess, "run", fake_run(b"0123456789abcdef"))

    output = func(b"bytecode")

    assert "0123456789" in output
    assert "abcdef" not in output
    assert "truncated" in output


def test_tool_output_capped_on_disk(monkeypatch):
    monkeypatch.setattr(inspector.deob, "MAX_OUTPUT", 10)
    start = time.monotonic()

    output = inspector.deob._run("yes", ["yes"], b"bytecode")

    assert time.monotonic() - start < inspector.deob.TOOL_TIMEOUT
    assert "truncated" in output


def test_disassemble_runs_xdis_with_this_interpreter(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return pretend.stub(returncode=0)

    monkeypatch.setattr(subprocess, "run", run)

    disassemble(b"bytecode")

    [args] = calls
    assert args[-5:] == [sys.executable, "-I", "-m", "xdis.bin.pydisasm", "file.pyc"]


def test_tool_timeout_after_truncation(monkeypatch):
    monkeypatch.setattr(inspector.deob, "MAX_OUTPUT", 10)

    def run(args, **kwargs):
        kwargs["stdout"].write(b"0123456789abcdef")
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", run)

    output = decompile(b"bytecode")

    assert "truncated" in output
    assert "timed out" in output


def test_tool_runs_without_python_in_the_child(monkeypatch):
    def run(args, **kwargs):
        assert "preexec_fn" not in kwargs
        return pretend.stub(returncode=0)

    monkeypatch.setattr(subprocess, "run", run)

    decompile(b"bytecode")


def test_disassemble_hides_runtime_banner(monkeypatch):
    banner = (
        b"# pydisasm version 6.3.0\n"
        b"# CPython Python bytecode 3.14 (3627)\n"
        b"#   Disassembled from CPython Python 3.15.2 (main) [GCC 14.2.0]\n"
    )
    monkeypatch.setattr(subprocess, "run", fake_run(banner))

    output = disassemble(b"bytecode")

    assert "Python bytecode 3.14" in output
    assert "GCC" not in output
