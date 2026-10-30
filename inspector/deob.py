"""
This module contains functions for decompiling and disassembling files.
"""

import signal
import subprocess
import sys
import tempfile

from pathlib import Path

DISASM_HEADER = "This file was disassembled from bytecode by Inspector using xdis."
DECOMPILE_HEADER = (
    '"""\n'
    "This file was decompiled from bytecode by Inspector using pycdc.\n"
    "The code below may be incomplete or syntactically incorrect.\n"
    '"""\n\n'
)


# Both tools run in the request, after the PyPI lookups and the download,
# and gunicorn kills workers after 10 seconds.
TOOL_TIMEOUT = 3
MAX_OUTPUT = 1024 * 1024


def _run(name: str, args: list[str], code: bytes) -> str:
    # Cap the output file in a shell rather than a preexec_fn, which isn't safe
    # once Sentry has started its threads. ulimit counts 512-byte blocks.
    limit = f'ulimit -S -f {MAX_OUTPUT // 512 + 1} 2>/dev/null; exec "$@"'
    notes = []
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "file.pyc").write_bytes(code)
        with open(Path(tmpdir, "output"), "w+b") as output:
            try:
                completed = subprocess.run(
                    ["sh", "-c", limit, name, *args, "file.pyc"],
                    cwd=tmpdir,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=TOOL_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                notes.append(f"{name} timed out after {TOOL_TIMEOUT} seconds.\n")
            except OSError as exc:
                return f"{name} could not run: {exc.strerror or exc}.\n"
            else:
                if completed.returncode not in (0, -signal.SIGXFSZ):
                    notes.append(f"{name} exited with status {completed.returncode}.\n")

            output.seek(0)
            result = output.read(MAX_OUTPUT + 1)

    text = result[:MAX_OUTPUT].decode(errors="backslashreplace")
    if len(result) > MAX_OUTPUT:
        notes.insert(0, f"{name} output truncated at {MAX_OUTPUT} bytes.\n")
    if notes:
        text += "\n\n" + "".join(notes)
    return text


def decompile(code: bytes) -> str:
    """
    Decompile bytecode using pycdc.
    """

    return DECOMPILE_HEADER + _run("pycdc", ["pycdc"], code)


def disassemble(code: bytes) -> str:
    # Drop pydisasm's banner line describing the server's own interpreter build.
    disassembly = "".join(
        line
        for line in _run(
            "pydisasm", [sys.executable, "-I", "-m", "xdis.bin.pydisasm"], code
        ).splitlines(keepends=True)
        if not line.startswith("#   Disassembled from ")
    )
    return DISASM_HEADER + "\n\n" + disassembly
