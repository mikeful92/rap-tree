import argparse
import csv
import json
import re
import sys
from datetime import date

import numpy as np

from . import clean, distance, fetch, tree
from .config import OUT_DIR, Artist, load_artists


def select(artists: list[Artist], only: list[str] | None) -> list[Artist]:
    if not only:
        return artists
    wanted = {o.lower() for o in only}
    picked = [a for a in artists if a.name.lower() in wanted or a.slug in wanted]
    missing = wanted - {a.name.lower() for a in picked} - {a.slug for a in picked}
    if missing:
        sys.exit(f"not in artists.csv: {', '.join(sorted(missing))}")
    return picked


def usable(artists: list[Artist], size: int, copies: int = 1) -> tuple[list[Artist], list[list[str]]]:
    keep, songs = [], []
    for a in artists:
        texts = distance.song_texts(a) if (distance.CLEAN_DIR / a.slug).exists() else []
        have = sum(len(t.encode()) for t in texts)
        if have >= size * copies:
            keep.append(a)
            songs.append(texts)
        else:
            print(f"  skipping {a.name}: {have / 1000:.1f} KB < {size * copies / 1000:.1f} KB needed")
    return keep, songs


def cmd_fetch(args):
    fetch.fetch(select(load_artists(), args.only), args.max_songs)


def cmd_clean(args):
    clean.clean(select(load_artists(), args.only))


def cmd_build(args):
    size, probe = int(args.sample_kb * 1000), int(args.probe_kb * 1000)
    artists, songs = usable(select(load_artists(), args.only), size)
    if len(artists) < 3:
        sys.exit("need at least 3 artists with enough lyrics; run fetch and clean first")
    names = [a.name for a in artists]

    reps = []
    for seed in range(max(args.replicates, 1)):
        samples = [distance.sample(s, size, seed) for s in songs]
        reps.append(distance.distance_matrix(samples, args.compressor, args.measure, probe, args.workers))
        print(f"  replicate {seed + 1}/{max(args.replicates, 1)}", flush=True)
    D = np.mean(reps, axis=0)
    t = tree.build_tree(D, names, reps if args.replicates > 1 else [])

    first = [distance.sample(s, size, 0) for s in songs]
    info = []
    for k, a in enumerate(artists):
        words = re.findall(r"[a-z0-9']+", first[k].decode())
        order = np.argsort(D[k])
        info.append(
            {
                "name": a.name,
                "region": a.region,
                "era": a.era,
                "songs": len(songs[k]),
                "corpus_bytes": sum(len(x.encode()) for x in songs[k]),
                "unique_words": len(set(words)),
                "compression_ratio": round(distance.compressed_size(first[k], args.compressor) / size, 4),
                "nearest": [
                    {"name": names[j], "distance": round(float(D[k, j]), 5)} for j in order if j != k
                ][:5],
            }
        )

    out = OUT_DIR / args.out
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "measure": args.measure,
        "compressor": args.compressor,
        "sample_bytes": size,
        "probe_bytes": probe if args.measure == "benedetto" else None,
        "replicates": args.replicates,
        "built": date.today().isoformat(),
    }
    (out / "tree.json").write_text(json.dumps({"meta": meta, "artists": info, "tree": t}, indent=1))
    (out / "tree.nwk").write_text(tree.to_newick(t) + "\n")
    with open(out / "distances.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["artist", *names])
        for name, row in zip(names, D):
            w.writerow([name, *(f"{x:.5f}" for x in row)])
    print(f"wrote {out}/tree.json, tree.nwk, distances.csv ({len(names)} artists)")


def cmd_validate(args):
    """Two disjoint samples per artist: each half's nearest neighbor should be its twin."""
    size, probe = int(args.sample_kb * 1000), int(args.probe_kb * 1000)
    artists, songs = usable(select(load_artists(), args.only), size, copies=2)
    if len(artists) < 2:
        sys.exit("need at least 2 artists with 2x sample size of lyrics")
    samples, labels = [], []
    for a, s in zip(artists, songs):
        for half in (0, 1):
            samples.append(distance.sample(s, size, seed=0, skip=half))
            labels.append(a.name)
    D = distance.distance_matrix(samples, args.compressor, args.measure, probe, args.workers)
    np.fill_diagonal(D, np.inf)
    hits = 0
    for i, name in enumerate(labels):
        j = int(np.argmin(D[i]))
        ok = labels[j] == name
        hits += ok
        if not ok:
            print(f"  miss: {name} #{i % 2 + 1} -> {labels[j]}")
    print(f"self-identification: {hits}/{len(labels)} = {hits / len(labels):.0%}")


def main():
    p = argparse.ArgumentParser(prog="raptree")
    sub = p.add_subparsers(required=True)

    def common(sp):
        sp.add_argument("--only", nargs="+", metavar="ARTIST", help="limit to these artists")

    def analysis(sp):
        common(sp)
        sp.add_argument("--measure", choices=["benedetto", "ncd"], default="benedetto")
        sp.add_argument("--compressor", choices=["lzma", "zstd", "bz2", "gzip"], default="lzma")
        sp.add_argument("--sample-kb", type=float, default=30, help="bytes of lyrics per artist")
        sp.add_argument("--probe-kb", type=float, default=3, help="appended chunk size (benedetto)")
        sp.add_argument("--workers", type=int, default=None)

    sp = sub.add_parser("fetch", help="download lyrics from Genius")
    common(sp)
    sp.add_argument("--max-songs", type=int, default=60)
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("clean", help="normalize lyrics, drop guest verses and repeated lines")
    common(sp)
    sp.set_defaults(func=cmd_clean)

    sp = sub.add_parser("build", help="compute distances and the tree")
    analysis(sp)
    sp.add_argument("--replicates", type=int, default=20, help="resamples for support values")
    sp.add_argument("--out", default="latest", help="subfolder of docs/data")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("validate", help="check each artist is closest to itself")
    analysis(sp)
    sp.set_defaults(func=cmd_validate)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
