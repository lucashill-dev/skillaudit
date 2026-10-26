"""Reporting layer: result CSVs, the run manifest, and charts.

findings.csv and summary.csv are canonical (sorted rows, sorted JSON keys, '\n'
line endings, no timestamps), so the same input always gives byte-identical
files; Q2 compares their hashes. Timings and memory (Q4) go in manifest.json,
which is expected to differ between runs. The baseline writes the same CSVs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import resource
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

from skillaudit.checks.base import Finding

FINDINGS_FILE = "findings.csv"
SUMMARY_FILE = "summary.csv"
MANIFEST_FILE = "manifest.json"
RESULT_FILES = (FINDINGS_FILE, SUMMARY_FILE)


# ------------------------------------------------------------------ CSVs
def write_findings(path: Path, findings: List[Finding]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["check", "skill_id", "file_sha", "flagged", "reason", "evidence"])
        for f in sorted(findings, key=lambda f: (f.check, f.skill_id, f.reason)):
            w.writerow([f.check, f.skill_id, f.file_sha, int(f.flagged), f.reason,
                        f.evidence_json()])


def summarise(findings: Iterable[Finding], check_names: Iterable[str]) -> List[Dict]:
    """One row per check: how many skills it applied to, how many it flagged,
    and how many got each reason code."""
    evaluated: Counter = Counter()
    flagged: Counter = Counter()
    reasons: Dict[str, Counter] = defaultdict(Counter)
    for f in findings:
        evaluated[f.check] += 1
        flagged[f.check] += int(f.flagged)
        reasons[f.check][f.reason] += 1
    rows = []
    for name in sorted(check_names):
        n, k = evaluated[name], flagged[name]
        rows.append({
            "check": name,
            "evaluated": n,
            "flagged": k,
            "pct_flagged": f"{100.0 * k / n:.2f}" if n else "",
            "reasons": json.dumps(dict(sorted(reasons[name].items())),
                                  separators=(",", ":")),
        })
    return rows


def write_summary(path: Path, rows: List[Dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, lineterminator="\n",
                           fieldnames=["check", "evaluated", "flagged", "pct_flagged", "reasons"])
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ manifest
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux kilobytes.
    return round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def git_commit() -> Dict[str, object]:
    here = Path(__file__).resolve().parent
    try:
        def git(*args):
            return subprocess.run(["git", *args], cwd=here, capture_output=True,
                                  text=True, timeout=10, check=True).stdout.strip()
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def write_manifest(out_dir: Path, *, implementation: str, version: str, config: dict,
                   dataset: dict, checks: Iterable[str], as_of: str, counts: dict,
                   timings: dict) -> Path:
    manifest = {
        "implementation": implementation,
        "version": version,
        "git": git_commit(),
        "environment": {"python": platform.python_version(),
                        "platform": platform.platform(), "machine": platform.machine()},
        "config": config,
        "dataset": dataset,
        "as_of": as_of,
        "checks": sorted(checks),
        "counts": counts,
        "outputs": {name: sha256_file(out_dir / name) for name in RESULT_FILES},
        "timings_seconds": {k: round(v, 3) for k, v in timings.items()},
        "peak_rss_mb": peak_rss_mb(),
    }
    path = out_dir / MANIFEST_FILE
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------ charts
def make_charts(run_dir) -> List[Path]:
    """Draw charts from a finished run's CSVs (needs matplotlib)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise RuntimeError("charts need matplotlib: pip install -e '.[charts]'") from e

    run_dir = Path(run_dir)
    out = run_dir / "charts"
    out.mkdir(exist_ok=True)
    written = []

    # E1-E3 headline: % of evaluated skills flagged by each check.
    with open(run_dir / SUMMARY_FILE, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["pct_flagged"]]
    if rows:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        pct = [float(r["pct_flagged"]) for r in rows]
        bars = ax.barh([r["check"] for r in rows], pct, color="#4C72B0")
        for bar, r in zip(bars, rows):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                    f'{r["flagged"]}/{r["evaluated"]}', va="center", fontsize=8)
        ax.set_xlabel("% of evaluated skills flagged")
        ax.set_xlim(0, max(100.0, max(pct) * 1.15))
        ax.invert_yaxis()
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        written.append(out / "flag_rates.png")
        fig.savefig(written[-1], dpi=150)
        plt.close(fig)

    # E3: are skills that ship executables copied more widely?
    with_exec, without = [], []
    with open(run_dir / FINDINGS_FILE, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["check"] == "bundled_executables":
                copies = json.loads(r["evidence"]).get("copy_count", 1)
                (with_exec if r["flagged"] == "1" else without).append(copies)
    if with_exec or without:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.boxplot([without or [0], with_exec or [0]], positions=[1, 2])
        ax.set_xticks([1, 2], ["no executables", "has executables"])
        ax.set_yscale("log")
        ax.set_ylabel("occurrences of identical content")
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        written.append(out / "copies_by_executables.png")
        fig.savefig(written[-1], dpi=150)
        plt.close(fig)
    return written
