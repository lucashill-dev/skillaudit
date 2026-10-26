"""Data-access layer: reads the official GitSkills SQLite release.

The MSR 2027 challenge distributes the dataset as one SQLite file
(agent_skills_sample.db for the 277 MB sample, 41 GB for the full dataset).
This is the only module that knows about the database; everything above it
works with plain dict rows. It uses Python's built-in sqlite3, opens the file
read-only, and reads only the columns the tool needs.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple

ARTIFACTS = "artifacts"
SIBLINGS = "artifact_siblings"
REPOS = "repos"

# Only the columns the parsing layer uses.
TABLE_COLUMNS: Dict[str, Tuple[str, ...]] = {
    ARTIFACTS: (
        "repo_full_name", "path", "file_sha", "discovered_at", "content", "name",
        "dedup_primary", "history_fetched", "composition_fetched",
        "first_commit_at", "last_commit_at", "commit_count",
    ),
    SIBLINGS: ("repo_full_name", "artifact_path", "entry_name", "entry_type"),
    REPOS: ("full_name", "pushed_at"),
}

SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
HASH_LIMIT_BYTES = 1024 ** 3  # hash the sample (277 MB); skip the 41 GB full file
BATCH_SIZE = 50_000

Row = Dict[str, object]


class DataError(RuntimeError):
    pass


def find_database(path) -> Path:
    """Accept the .db file itself or a folder containing exactly one."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() in SQLITE_SUFFIXES:
        return p
    if p.is_dir():
        found = sorted(f for f in p.iterdir()
                       if f.is_file() and f.suffix.lower() in SQLITE_SUFFIXES)
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise DataError(f"several SQLite files in {p}; pass one with --data")
    raise DataError(f"no GitSkills SQLite file found at {p}")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class Dataset:
    """Read-only access to one GitSkills SQLite file."""

    def __init__(self, path):
        self.path = find_database(path)
        self.con = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)

    def rows(self, table: str) -> Iterator[Row]:
        """Yield rows of ``table`` with only TABLE_COLUMNS (missing ones as None)."""
        existing = {r[1] for r in self.con.execute(f"PRAGMA table_info({_quote(table)})")}
        if not existing:
            raise DataError(f"table '{table}' not found in {self.path.name}")
        wanted = TABLE_COLUMNS[table]
        select = ", ".join(_quote(c) if c in existing else f"NULL AS {_quote(c)}"
                           for c in wanted)
        cur = self.con.execute(f"SELECT {select} FROM {_quote(table)}")
        while True:
            batch = cur.fetchmany(BATCH_SIZE)
            if not batch:
                break
            for r in batch:
                yield dict(zip(wanted, r))

    def describe(self) -> dict:
        """What was read, for the run manifest."""
        size = self.path.stat().st_size
        digest: Optional[str] = None
        if size <= HASH_LIMIT_BYTES:
            h = hashlib.sha256()
            with open(self.path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            digest = h.hexdigest()
        return {"file": self.path.name, "bytes": size, "sha256": digest,
                "sqlite_version": sqlite3.sqlite_version}
