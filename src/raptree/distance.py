"""Compression distances between artists.

Two measures:

ncd        Normalized Compression Distance (Cilibrasi & Vitanyi 2005)
           (C(xy) - min(C(x), C(y))) / max(C(x), C(y))

benedetto  "Language Trees and Zipping" (Benedetto, Caglioti & Loreto 2002).
           Take the last chunk b of artist B, append it to artist A's text,
           and see how many extra bytes it costs to compress:
               delta(A, b) = C(A + b) - C(A)
           Compare with appending it to B's own earlier text:
               S(A, B) = (delta(A, b) - delta(B, b)) / |b|
           i.e. extra bytes per character when A's style is used to encode B.
           Symmetrized as (S(A, B) + S(B, A)) / 2.

Every artist gets exactly the same number of bytes, because compressed size
depends on input size and an uneven corpus would skew distances.
"""

import bz2
import lzma
import random
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from .config import CLEAN_DIR, Artist

try:
    from compression import zstd  # Python 3.14+
except ImportError:
    zstd = None

LZMA_FILTERS = [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME}]


def compressed_size(data: bytes, method: str) -> int:
    if method == "lzma":
        return len(lzma.compress(data, format=lzma.FORMAT_RAW, filters=LZMA_FILTERS))
    if method == "zstd":
        if zstd is None:
            raise SystemExit("zstd needs Python 3.14+; use --compressor lzma")
        return len(zstd.compress(data, level=19))
    if method == "bz2":
        return len(bz2.compress(data, 9))
    if method == "gzip":  # 32 KB window: only valid for small samples
        return len(zlib.compress(data, 9))
    raise ValueError(f"unknown compressor {method!r}")


def song_texts(artist: Artist) -> list[str]:
    return [p.read_text() for p in sorted((CLEAN_DIR / artist.slug).glob("*.txt"))]


def corpus_bytes(artist: Artist) -> int:
    return sum(len(t.encode()) for t in song_texts(artist))


def sample(songs: list[str], size: int, seed: int, skip: int = 0) -> bytes | None:
    """`size` bytes of whole songs in random order (cut to exact size).

    `skip` samples are discarded first, giving disjoint samples for validation.
    """
    order = list(songs)
    random.Random(seed).shuffle(order)
    data = "".join(order).encode()
    start = skip * size
    if len(data) < start + size:
        return None
    return data[start : start + size]


# Worker plumbing: samples are shared with workers once via the initializer
# instead of being pickled for every pair.
_SAMPLES: list[bytes] = []
_METHOD = "lzma"


def _init(samples: list[bytes], method: str) -> None:
    global _SAMPLES, _METHOD
    _SAMPLES, _METHOD = samples, method


def _size_concat(job: tuple) -> int:
    i, j, cut = job  # C(x_i[:cut] + x_j[cut:]) ; cut=None means plain concat
    if cut is None:
        data = _SAMPLES[i] + (_SAMPLES[j] if j is not None else b"")
    else:
        data = _SAMPLES[i][:cut] + _SAMPLES[j][cut:]
    return compressed_size(data, _METHOD)


def _run(jobs: list[tuple], samples: list[bytes], method: str, pool_size: int | None):
    with ProcessPoolExecutor(pool_size, initializer=_init, initargs=(samples, method)) as ex:
        return list(ex.map(_size_concat, jobs, chunksize=8))


def ncd_matrix(samples: list[bytes], method: str, workers: int | None = None) -> np.ndarray:
    n = len(samples)
    singles = [(i, None, None) for i in range(n)]
    pairs = [(i, j, None) for i in range(n) for j in range(n) if i != j]
    sizes = _run(singles + pairs, samples, method, workers)
    c = np.array(sizes[:n], float)
    D = np.zeros((n, n))
    for (i, j, _), cxy in zip(pairs, sizes[n:]):
        D[i, j] = (cxy - min(c[i], c[j])) / max(c[i], c[j])
    return (D + D.T) / 2


def benedetto_matrix(
    samples: list[bytes], method: str, probe: int, workers: int | None = None
) -> np.ndarray:
    n = len(samples)
    cut = len(samples[0]) - probe
    # ref_i = sample i minus its last `probe` bytes; probe_i = those bytes
    refs = [s[:cut] for s in samples]
    ref_sizes = _run([(i, None, None) for i in range(n)], refs, method, workers)
    jobs = [(i, j, cut) for i in range(n) for j in range(n)]
    sizes = _run(jobs, samples, method, workers)
    delta = np.zeros((n, n))  # delta[i, j] = C(ref_i + probe_j) - C(ref_i)
    for (i, j, _), s in zip(jobs, sizes):
        delta[i, j] = s - ref_sizes[i]
    S = (delta - np.diag(delta)[None, :]) / probe  # S[i, j]: cost of coding j with i
    D = (S + S.T) / 2
    np.fill_diagonal(D, 0)
    return np.clip(D, 0, None)


def distance_matrix(samples, method, measure, probe, workers=None) -> np.ndarray:
    if measure == "ncd":
        return ncd_matrix(samples, method, workers)
    if measure == "benedetto":
        return benedetto_matrix(samples, method, probe, workers)
    raise ValueError(f"unknown measure {measure!r}")
