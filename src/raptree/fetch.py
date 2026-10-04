"""Download lyrics from Genius.

Raw lyrics go to data/raw/<artist>/<song_id>.json (gitignored, copyrighted).
A metadata manifest (title, url, release date; no lyrics) goes to
data/manifest/<artist>.csv so the corpus is reproducible from the public repo.
Re-running skips songs already on disk, so an interrupted fetch can resume.
"""

import csv
import json
import os
import re
import sys

from .config import MANIFEST_DIR, RAW_DIR, Artist, load_dotenv

SKIP_TITLE = re.compile(
    r"\b(remix|live|skit|instrumental|demo|acapella|a cappella|translation|"
    r"traducción|tradução|übersetzung|traduction|clean|radio edit|sped up|slowed)\b",
    re.IGNORECASE,
)


def client():
    import lyricsgenius

    load_dotenv()
    token = os.environ.get("GENIUS_ACCESS_TOKEN")
    if not token:
        sys.exit("GENIUS_ACCESS_TOKEN is not set. Copy .env.example to .env and fill it in.")
    return lyricsgenius.Genius(token, timeout=20, retries=3, sleep_time=0.5)


def list_songs(genius, artist_id: int, max_songs: int) -> list[dict]:
    """Most popular songs where the artist is the primary artist."""
    songs, page = [], 1
    while page and len(songs) < max_songs:
        res = genius.artist_songs(artist_id, per_page=50, page=page, sort="popularity")
        for s in res["songs"]:
            if s["primary_artist"]["id"] != artist_id:
                continue
            if s.get("lyrics_state") != "complete" or SKIP_TITLE.search(s["title"]):
                continue
            songs.append(s)
        page = res.get("next_page")
    return songs[:max_songs]


def fetch_artist(genius, artist: Artist, max_songs: int) -> None:
    found = genius.search_artist(artist.name, max_songs=0, get_full_info=False)
    if found is None:
        print(f"  !! no Genius artist found for {artist.name!r}")
        return
    artist_id = found._body["id"]  # lyricsgenius's Artist type doesn't expose id
    print(f"{artist.name} -> Genius: {found.name} (id {artist_id})")

    out_dir = RAW_DIR / artist.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    songs = list_songs(genius, artist_id, max_songs)

    rows = []
    for i, s in enumerate(songs, 1):
        path = out_dir / f"{s['id']}.json"
        if not path.exists():
            try:
                lyrics = genius.lyrics(song_url=s["url"])
            except Exception as e:  # network hiccups, 403s: skip and retry next run
                print(f"  !! {s['title']}: {e}")
                continue
            if not lyrics:
                continue
            path.write_text(
                json.dumps(
                    {
                        "id": s["id"],
                        "title": s["title"],
                        "url": s["url"],
                        "genius_artist": found.name,
                        "lyrics": lyrics,
                    },
                    ensure_ascii=False,
                )
            )
            print(f"  [{i}/{len(songs)}] {s['title']}")
        rows.append(
            {
                "song_id": s["id"],
                "title": s["title"],
                "release_date": s.get("release_date_for_display") or "",
                "url": s["url"],
            }
        )

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_DIR / f"{artist.slug}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["song_id", "title", "release_date", "url"])
        w.writeheader()
        w.writerows(rows)


def fetch(artists: list[Artist], max_songs: int) -> None:
    genius = client()
    for a in artists:
        fetch_artist(genius, a, max_songs)
