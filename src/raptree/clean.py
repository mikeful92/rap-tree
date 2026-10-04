"""Turn raw Genius lyrics into one normalized text per artist.

- drops Genius page junk (contributor counts, "Embed", ticket ads)
- keeps only sections performed by the artist: a header like
  "[Verse 2: Jay Rock]" that names only other people is dropped, while an
  unattributed header ("[Chorus]") is assumed to be the primary artist
- lowercases, strips punctuation (keeps apostrophes), keeps ad-libs as words
- removes lines already seen anywhere in the artist's corpus, so repeated
  hooks don't make an artist look artificially compressible
"""

import json
import re
import unicodedata

from .config import CLEAN_DIR, RAW_DIR, Artist

HEADER = re.compile(r"^\s*\[([^\]]*)\]\s*$")
JUNK = [
    re.compile(r"^\d*\s*contributors?\b", re.I),
    re.compile(r"read more$", re.I),
    re.compile(r"^you might also like", re.I),
    re.compile(r"^see .* live$", re.I),
    re.compile(r"^get tickets as low as", re.I),
    re.compile(r"^\d*embed$", re.I),
]
NAME_SPLIT = re.compile(r"\s*(?:&|,|\+|\band\b|\bwith\b|/)\s*", re.I)


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9$]", "", s.lower())


def header_names(header: str) -> list[str] | None:
    """Performer names in a section header, or None if unattributed."""
    if ":" not in header:
        return None
    who = header.split(":", 1)[1]
    who = re.sub(r"[()*]", ",", who)  # "[Chorus: Drake (Future)]" -> both
    names = [norm_name(n) for n in NAME_SPLIT.split(who)]
    return [n for n in names if n] or None


def norm_line(line: str) -> str:
    line = unicodedata.normalize("NFKC", line).replace("’", "'").replace("‘", "'")
    line = line.lower()
    line = re.sub(r"[^a-z0-9'\s]", " ", line)
    return re.sub(r"\s+", " ", line).strip()


def artist_sections(lyrics: str, names: set[str]) -> list[str]:
    """Lines from the sections this artist performs."""
    keep, out = True, []
    lines = lyrics.strip().splitlines()
    if lines and re.search(r"(contributors|lyrics)$", lines[0], re.I):
        lines = lines[1:]  # "Song Title Lyrics" page header
    for line in lines:
        line = re.sub(r"\d*Embed$", "", line.strip())
        m = HEADER.match(line)
        if m:
            performers = header_names(m.group(1))
            keep = performers is None or any(p in names for p in performers)
            continue
        if not line or any(j.search(line) for j in JUNK):
            continue
        if keep:
            out.append(line)
    return out


def clean_artist(artist: Artist) -> dict:
    src = RAW_DIR / artist.slug
    if not src.exists():
        return {"artist": artist.name, "songs": 0, "bytes": 0}
    songs = [json.loads(p.read_text()) for p in sorted(src.glob("*.json"))]
    names = {norm_name(n) for n in [artist.name, *artist.aliases]}
    names |= {norm_name(s["genius_artist"]) for s in songs}

    seen: set[str] = set()
    out_dir = CLEAN_DIR / artist.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.txt"):
        old.unlink()
    kept = 0
    total = 0
    for s in songs:
        lines = []
        for raw in artist_sections(s["lyrics"], names):
            line = norm_line(raw)
            if len(line) < 3 or line in seen:
                continue
            seen.add(line)
            lines.append(line)
        if lines:
            text = "\n".join(lines) + "\n"
            (out_dir / f"{s['id']}.txt").write_text(text)
            kept += 1
            total += len(text.encode())
    return {"artist": artist.name, "songs": kept, "bytes": total}


def clean(artists: list[Artist]) -> list[dict]:
    stats = []
    for a in artists:
        st = clean_artist(a)
        stats.append(st)
        print(f"{a.name:32s} {st['songs']:4d} songs {st['bytes'] / 1000:8.1f} KB")
    return stats
