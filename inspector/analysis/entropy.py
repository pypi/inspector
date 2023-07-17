from math import log2
import collections


def shannon_entropy(X: bytes):
    result = 0.0

    items = collections.Counter(X).items()
    for b, count in items:
        pr = count / len(X)
        result -= pr * log2(pr)

    return result
