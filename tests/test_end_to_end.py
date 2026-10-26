"""Whole-pipeline tests: CLI, reproducibility (Q2) and baseline parity."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import FIXTURE_DB

from skillaudit.cli import main as cli_main
from skillaudit.reporting import RESULT_FILES, sha256_file
from skillaudit.runner import run_audit

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline" / "skillaudit_single.py"


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_summary_matches_expected_counts(self):
        run_audit(FIXTURE_DB, self.tmp / "run")
        with open(self.tmp / "run" / "summary.csv", encoding="utf-8") as fh:
            rows = {r["check"]: r for r in csv.DictReader(fh)}
        counts = {c: (r["evaluated"], r["flagged"]) for c, r in rows.items()}
        self.assertEqual(counts, {"staleness": ("6", "2"), "risky_copy": ("4", "1"),
                                  "bundled_executables": ("6", "1")})
        self.assertEqual(rows["risky_copy"]["pct_flagged"], "25.00")
        self.assertEqual(json.loads(rows["staleness"]["reasons"]),
                         {"recently_updated": 3, "repo_inactive": 1, "stale": 2})

    def test_repeated_runs_are_byte_identical(self):
        a = run_audit(FIXTURE_DB, self.tmp / "a").out_dir
        b = run_audit(FIXTURE_DB, self.tmp / "b").out_dir
        for name in RESULT_FILES:
            self.assertEqual(sha256_file(a / name), sha256_file(b / name))

    def test_manifest_records_what_q2_and_q4_need(self):
        r = run_audit(FIXTURE_DB, self.tmp / "run")
        m = json.loads(r.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(m["implementation"], "layered")
        self.assertEqual(sorted(m["outputs"]), sorted(RESULT_FILES))
        self.assertEqual(m["as_of"], "2026-07-31T00:00:00+00:00")
        self.assertEqual(m["config"]["stale_days"], 180)
        self.assertEqual(len(m["dataset"]["sha256"]), 64)
        self.assertIn("total", m["timings_seconds"])
        self.assertGreater(m["peak_rss_mb"], 0)

    def test_check_subset(self):
        r = run_audit(FIXTURE_DB, self.tmp / "run", check_names=["staleness"])
        self.assertEqual({f.check for f in r.findings}, {"staleness"})

    def test_cli_run_and_list(self):
        out = self.tmp / "cli"
        self.assertEqual(cli_main(["run", "--data", str(FIXTURE_DB), "--out", str(out)]), 0)
        self.assertTrue((out / "findings.csv").exists())
        self.assertEqual(cli_main(["list-checks"]), 0)

    def test_baseline_produces_identical_results(self):
        """Both versions must agree before Q1 compares their structure."""
        layered = run_audit(FIXTURE_DB, self.tmp / "layered").out_dir
        base = self.tmp / "baseline"
        subprocess.run([sys.executable, str(BASELINE), "--data", str(FIXTURE_DB),
                        "--out", str(base)], check=True, capture_output=True)
        for name in RESULT_FILES:
            with self.subTest(file=name):
                self.assertEqual((layered / name).read_text(encoding="utf-8"),
                                 (base / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
