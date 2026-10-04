import random

import numpy as np

from raptree import clean, distance, tree


def test_section_attribution():
    lyrics = """Song Title Lyrics
[Intro]
yeah yeah
[Verse 1: Kendrick Lamar]
kendrick line
[Verse 2: Jay Rock]
jay rock line
[Chorus: Kendrick Lamar & SZA]
shared hook
[Verse 3: Jay Rock (Kendrick Lamar)]
ad-lib verse
[Outro: SZA]
sza line
[Skit]
mom on the phone
You might also like
4Embed"""
    names = {clean.norm_name("Kendrick Lamar"), clean.norm_name("K.Dot")}
    assert clean.artist_sections(lyrics, names) == [
        "yeah yeah",
        "kendrick line",
        "shared hook",
        "ad-lib verse",
    ]


def test_norm_line():
    assert clean.norm_line("I’m on (Yeah!) — the GRIND, 24/7") == "i'm on yeah the grind 24 7"
    assert clean.norm_name("Beyoncé") == clean.norm_name("beyonce")


def test_nj_recovers_additive_tree():
    # ((A:1,B:2):1,(C:1,D:3):1) as an additive distance matrix
    D = np.array(
        [
            [0, 3, 4, 6],
            [3, 0, 5, 7],
            [4, 5, 0, 4],
            [6, 7, 4, 0],
        ],
        float,
    )
    adj = tree.neighbor_joining(D)
    assert tree.splits(adj, 4) == {frozenset({2, 3})}
    t = tree.build_tree(D, list("ABCD"))
    leaves = sorted(
        [c["name"] for c in sub["children"]] for sub in t["children"] if "children" in sub
    )
    assert leaves == [["A", "B"], ["C", "D"]]
    assert tree.to_newick(t).endswith(";")


def fake_artist(vocab_seed: int, n_songs: int = 40) -> list[str]:
    """Songs from a private 'slang' vocabulary mixed with shared common words."""
    rng = random.Random(vocab_seed)
    common = "i the you my it on in we that a to and got get money real".split()
    slang = ["".join(rng.choices("abcdefghijklmnoprstuwyz", k=rng.randint(3, 7))) for _ in range(150)]
    songs = []
    for _ in range(n_songs):
        lines = [
            " ".join(rng.choice(slang if rng.random() < 0.5 else common) for _ in range(9))
            for _ in range(40)
        ]
        songs.append("\n".join(lines) + "\n")
    return songs


def test_compression_distance_separates_styles():
    songs = [fake_artist(s) for s in (1, 2, 3)]
    for measure in ("ncd", "benedetto"):
        # two disjoint samples from each artist: twin halves must be closest
        samples = [distance.sample(s, 8000, seed=0, skip=k) for s in songs for k in (0, 1)]
        D = distance.distance_matrix(samples, "lzma", measure, probe=1000, workers=2)
        np.fill_diagonal(D, np.inf)
        for i in range(len(samples)):
            assert int(np.argmin(D[i])) // 2 == i // 2, measure
