"""
This module contains functions for decompiling and disassembling files.
"""

import subprocess
import tempfile

DISASM_HEADER = "This file was disassembled from bytecode by Inspector using pycdas."
DECOMPILE_HEADER = (
    '"""\n'
    "This file was decompiled from bytecode by Inspector using pycdc.\n"
    "The code below may be incomplete or syntactically incorrect.\n"
    '"""\n\n'
)


def decompile(code: bytes) -> str:
    """
    Decompile bytecode using pycdc.
    """

    with tempfile.NamedTemporaryFile() as f:
        f.write(code)
        output = subprocess.Popen(
            ["pycdc", f.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

        output = b"".join([l for l in output.stdout.readlines()]).decode()

    return DECOMPILE_HEADER + output


def disassemble(code: bytes) -> str:
    with tempfile.NamedTemporaryFile() as f:
        f.write(code)
        output = subprocess.Popen(
            ["pycdas", f.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

        disassembly = b"".join([l for l in output.stdout.readlines()]).decode()

    return DISASM_HEADER + "\n\n" + disassembly
