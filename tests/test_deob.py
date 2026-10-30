import py_compile

from pathlib import Path

import pytest

from inspector.deob import disassemble

FIXTURES = Path(__file__).parent / "fixtures"


def test_disassemble_python_3_14():
    disassembly = disassemble((FIXTURES / "greet-3.14.pyc").read_bytes())

    assert "Python bytecode 3.14" in disassembly
    assert "greet" in disassembly
    assert "Unknown magic" not in disassembly


@pytest.mark.xfail(
    strict=True, reason="xdis 6.3.0 predates the Python 3.15 final magic number"
)
def test_disassemble_running_python(tmp_path):
    pyc = tmp_path / "test_deob.pyc"
    py_compile.compile(
        str(FIXTURES.parent / "test_deob.py"), cfile=str(pyc), doraise=True
    )

    disassembly = disassemble(pyc.read_bytes())

    assert "Unknown magic" not in disassembly
    assert "test_disassemble_running_python" in disassembly
