#!/usr/bin/env python3
"""Download the official GitSkills sample (MSR 2027 Mining Challenge).

    python scripts/fetch_sample.py              # -> data/agent_skills_sample.db
    skillaudit run --data data/agent_skills_sample.db --out runs/sample-1

The sample is published by the dataset authors at
https://github.com/giuseppedestefanis/gitskills-sample : 29,786 SKILL.md
occurrences, 13,000 distinct contents, 11,841 repositories, as one SQLite file
(87 MB zip, 277 MB unzipped). Every content group in it is complete (all
copies plus the representative with text), so the copy-based checks work on
it exactly as on the full dataset.

The full dataset (41 GB SQLite) is on Zenodo, DOI 10.5281/zenodo.21875637.
Download it by hand and pass the .db file to --data the same way.

Uses only the standard library.
"""

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

SAMPLE_URL = ("https://github.com/giuseppedestefanis/gitskills-sample/"
              "raw/main/agent_skills_sample.zip")
DB_NAME = "agent_skills_sample.db"


def download(url: str, dest: Path) -> None:
    print(f"downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data"), help="folder to put the .db in")
    ap.add_argument("--zip", type=Path,
                    help="use an already-downloaded agent_skills_sample.zip instead")
    ap.add_argument("--force", action="store_true", help="re-download even if the .db exists")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    db = args.out / DB_NAME
    if db.exists() and not args.force:
        print(f"{db} already exists (use --force to replace it)")
        return 0

    zip_path = args.zip or (args.out / "agent_skills_sample.zip")
    if args.zip is None:
        download(SAMPLE_URL, zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        member = next((m for m in zf.namelist() if m.endswith(DB_NAME)), None)
        if member is None:
            print(f"{DB_NAME} not found in {zip_path}", file=sys.stderr)
            return 1
        with zf.open(member) as src, open(db, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    if args.zip is None:
        zip_path.unlink()

    h = hashlib.sha256()
    with open(db, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    print(f"{db}  {db.stat().st_size / 1e6:.0f} MB  sha256 {h.hexdigest()}")
    print(f"next: skillaudit run --data {db} --out runs/sample-1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
