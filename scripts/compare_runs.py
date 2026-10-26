#!/usr/bin/env python3
"""Q2 / Q4 helper: compare result hashes, run time and memory across run folders.

    python scripts/compare_runs.py runs/lucas-1 runs/lucas-2 runs/justin-1 ...

Exits 1 if any result file differs between runs, so it can be used in CI.
Works on layered and baseline runs (both write the same result files).
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

RESULT_FILES = ("findings.csv", "summary.csv")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    args = ap.parse_args()

    rows = []
    for run in args.runs:
        manifest = {}
        if (run / "manifest.json").exists():
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        hashes = {f: (sha256(run / f) if (run / f).exists() else None) for f in RESULT_FILES}
        rows.append((run, manifest, hashes))

    width = max(len(str(r[0])) for r in rows)
    print(f"{'run':<{width}}  {'impl':<9}{'machine':<10}{'total_s':>9}{'peak_mb':>9}  "
          + "  ".join(f"{f[:-4]:<12}" for f in RESULT_FILES))
    for run, m, hashes in rows:
        env = m.get("environment", {})
        print(f"{str(run):<{width}}  {m.get('implementation', '?'):<9}"
              f"{str(env.get('machine', '?')):<10}"
              f"{m.get('timings_seconds', {}).get('total', float('nan')):>9.2f}"
              f"{m.get('peak_rss_mb', float('nan')):>9}  "
              + "  ".join(f"{(h or 'MISSING')[:12]:<12}" for h in hashes.values()))

    ok = True
    for f in RESULT_FILES:
        distinct = {h[f] for _, _, h in rows}
        same = len(distinct) == 1 and None not in distinct
        ok &= same
        print(f"{f:<14} {'IDENTICAL' if same else 'DIFFERENT'} across {len(rows)} runs")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
