# rap-tree

A family tree of rap artists built only from **how well their lyrics compress together**.

The idea comes from Benedetto, Caglioti & Loreto, [*Language Trees and Zipping*](https://arxiv.org/abs/cond-mat/0108530) (2002). They built a family tree of European languages with gzip: append a short chunk of text B to a longer text A, compress, and measure how many extra bytes the chunk costs. If A and B share words, spellings and phrasing, the compressor reuses A's patterns and the chunk is cheap. Repeat this for every pair of artists and you get a distance matrix. Neighbor-joining turns that matrix into a tree.

The tree is published as a static page in [`docs/`](docs/index.html) (GitHub Pages).

## What's in the repo (and what isn't)

Lyrics are copyrighted, so **no lyrics are committed**. `data/raw/` and `data/clean/` are gitignored.

| Published | Path |
|---|---|
| Artist list with region / era tags | `artists.csv` |
| Song manifest per artist (Genius id, title, release date, URL), enough to rebuild the corpus | `data/manifest/*.csv` |
| Distance matrix, tree (Newick + JSON), per-artist stats | `docs/data/<build>/` |
| Interactive tree viewer | `docs/index.html` |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # paste your Genius Client Access Token
```

Get a token at <https://genius.com/api-clients>. The "App Website URL" field can be any URL, e.g. this repo's GitHub URL.

## Run

```bash
raptree fetch            # ~60 most popular songs per artist (resumable; re-run to fill gaps)
raptree clean            # normalize text, drop guest verses and repeated hooks
raptree validate         # sanity check: two disjoint samples of each artist should match each other
raptree build            # distances + tree -> docs/data/latest/
python3 -m http.server -d docs 8000   # view at http://localhost:8000
```

Useful flags:

- `--only "Kendrick Lamar" "J. Cole"`: run on a subset
- `--measure ncd|benedetto`: Normalized Compression Distance (default) or the paper's append-a-chunk distance
- `--compressor lzma|zstd|bz2|gzip`: lzma by default. gzip only looks back 32 KB, so it can't "see" a larger reference text
- `--sample-kb 60 --probe-kb 3`: bytes of lyrics per artist, and size of the appended chunk (`benedetto` only)
- `--replicates 20`: resample songs N times; branch numbers show the % of resampled trees that contain the same group
- `build --out <name>`: write to `docs/data/<name>/`, view with `?build=<name>`

## Method details

1. **Fetch.** For each artist in `artists.csv`, take their most popular Genius songs where they are the *primary* artist. Remixes, live versions, skits and translations are skipped.
2. **Clean.**
   - Genius section headers say who performs each part (`[Verse 2: Jay Rock]`). Sections credited only to other people are dropped, so features don't leak style between artists. Unattributed sections count as the primary artist's. For groups (Migos, OutKast…) the `aliases` column lists members, so their verses are kept.
   - Text is lowercased and stripped of punctuation except apostrophes. Ad-libs are kept as words.
   - A line that already appeared anywhere in the artist's corpus is dropped. Otherwise a hook repeated 4× would make that artist look very "compressible".
3. **Sample.** Every artist contributes exactly the same number of bytes (default 60 KB), taken from their songs in random order. Artists without enough lyrics are skipped with a message.
4. **Distance** (`ncd`, default). [Normalized Compression Distance](https://arxiv.org/abs/cs/0312044) (Cilibrasi & Vitányi, 2005), the symmetric successor to the Benedetto approach:
   `NCD(A,B) = (C(A+B) − min(C(A), C(B))) / max(C(A), C(B))`, where `C` is the lzma-compressed size.
   If B shares A's vocabulary and phrasing, compressing them together barely costs more than A alone.
   The paper's original append-a-chunk measure is available as `--measure benedetto`:
   `S(A,B) = ([C(ref_A + b) − C(ref_A)] − [C(ref_B + b) − C(ref_B)]) / |b|`, with `b` the last few KB of B.
5. **Tree.** Neighbor-joining on the distance matrix averaged over the resamples, rooted at the midpoint.
6. **Closest artists.** Some artists sit close to everyone because their vocabulary is near the middle of the corpus. The per-artist lists therefore rank pairs by how much closer they are than their average distances predict: `(m_A + m_B − m̄ − d_AB) / (m_A + m_B − m̄)`. Neighbor-joining is unaffected by this adjustment.

### Validation

`raptree validate` takes two non-overlapping 30 KB samples (different songs) per artist and checks whether each sample's nearest neighbor among all 132 samples is its own twin. On the 66-artist corpus:

| Setting | Self-identification |
|---|---|
| `ncd`, lzma (default) | 130/132 (98%) |
| `ncd`, zstd | 128/132 (97%) |
| `benedetto`, lzma, 8 KB chunk | 117/132 (89%) |
| `benedetto`, lzma, 3 KB chunk | 87/132 (66%) |

Chance would be under 1%. The appended-chunk measure gets noisy when the chunk is small, so NCD is the default.

Distances between different artists are tightly packed (NCD 0.90–0.95), since most of any verse is ordinary English. Larger samples matter for the tree: going from 30 KB to 60 KB per artist raised the number of groupings that reappear in at least half of the resampled trees from 4 to 18 (out of 64).

### Caveats

Compression sees surface text: vocabulary, slang, spellings, names, ad-libs. It doesn't see flow, delivery or meaning. Expect strong pull from **era** and **region**, plus artifacts from Genius transcription style, which varies by who transcribed a song. Ghostwriting also blurs the picture.

## Adding artists

Add a row to `artists.csv`: `name` is the Genius search term, and `aliases` are other names used in section headers (`;`-separated). Then run `raptree fetch --only "<name>"`, `raptree clean` and `raptree build`.

## License

- Code: [MIT](LICENSE)
- Generated data (`docs/data/`, `artists.csv`): [CC BY 4.0](LICENSE-DATA)
- Lyrics are not included and remain the property of their copyright holders.
