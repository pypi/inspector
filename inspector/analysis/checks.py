from hashlib import sha256
from typing import Any, Generator

from inspector.analysis.codedetails import Detail, DetailSeverity
from inspector.analysis.entropy import shannon_entropy
from inspector.distribution import GemDistribution


def __is_compiled(filepath: str) -> bool:
    return filepath.endswith(".pyc") or filepath.endswith(".pyo")


def basic_details(
    distribution: GemDistribution, filepath: str
) -> Generator[Detail, Any, None]:
    contents = distribution.contents(filepath)

    yield Detail(
        severity=DetailSeverity.NORMAL,
        prop_name="SHA-256",
        value=sha256(contents).hexdigest(),
    )

    entropy = shannon_entropy(contents)
    ent_suspicious = entropy > 6.0
    yield Detail(
        severity=DetailSeverity.HIGH if ent_suspicious else DetailSeverity.NORMAL,
        prop_name="Entropy",
        value=str(entropy) + " (HIGH)" if ent_suspicious else str(entropy),
    )

    if __is_compiled(filepath):
        yield Detail(
            severity=DetailSeverity.MEDIUM, prop_name="Compiled Python Bytecode"
        )
