import csv
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTISTS_CSV = ROOT / "artists.csv"
RAW_DIR = ROOT / "data" / "raw"  # gitignored: scraped lyrics
CLEAN_DIR = ROOT / "data" / "clean"  # gitignored: cleaned lyrics
MANIFEST_DIR = ROOT / "data" / "manifest"  # published: song titles/urls only
OUT_DIR = ROOT / "docs" / "data"  # published: distances, trees, stats


@dataclass
class Artist:
    name: str
    region: str
    era: str
    aliases: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return slugify(self.name)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("$", "s")).strip("-")


def load_artists(path: Path = ARTISTS_CSV) -> list[Artist]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Artist(
                name=row["name"].strip(),
                region=row["region"].strip(),
                era=row["era"].strip(),
                aliases=[a.strip() for a in row["aliases"].split(";") if a.strip()],
            )
            for row in csv.DictReader(f)
        ]


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
