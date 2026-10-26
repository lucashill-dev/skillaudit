"""Expected results for each check on the fixture set (see make_fixtures.py)."""

import unittest

from tests import findings_by_skill

from skillaudit.checks.risky_copy import jaccard, risky_features
from skillaudit.config import AuditConfig

A1 = "alpha/webapp:.claude/skills/pdf-tools/SKILL.md"
A2 = "beta/site:.claude/skills/pdf-tools/SKILL.md"
A3 = "gamma/tools:skills/pdf-tools/SKILL.md"
A4 = "delta/notes:skills/pdf-tools/SKILL.md"
A5 = "epsilon/infra:.claude/skills/deploy-helper/SKILL.md"
A6 = "zeta/ops:.claude/skills/deploy-helper/SKILL.md"
A7 = "eta/docs:skills/writing-style/SKILL.md"
A8 = "theta/misc:skills/untitled/SKILL.md"
A9 = "iota/app:skills/helper/SKILL.md"


def reasons(findings):
    return {sid: f.reason for sid, f in findings.items()}


class StalenessTests(unittest.TestCase):
    def test_expected_results(self):
        f = findings_by_skill("staleness")
        self.assertEqual(reasons(f), {
            A1: "stale",
            A2: "recently_updated",
            A3: "recently_updated",
            A5: "repo_inactive",
            A6: "stale",
            A8: "recently_updated",
        })
        self.assertEqual(sorted(s for s, x in f.items() if x.flagged), [A1, A6])
        self.assertEqual(f[A1].evidence["skill_age_days"], 332)  # 2025-09-01T10:00 -> 2026-07-31
        self.assertEqual(f[A1].evidence["repo_push_age_days"], 11)

    def test_skills_without_history_are_not_applicable(self):
        f = findings_by_skill("staleness")
        for sid in (A4, A7, A9):
            self.assertNotIn(sid, f)

    def test_cutoffs_are_configurable(self):
        f = findings_by_skill("staleness", AuditConfig(stale_days=400))
        self.assertFalse(any(x.flagged for x in f.values()))
        f = findings_by_skill("staleness", AuditConfig(stale_days=30, active_days=30))
        self.assertEqual(sorted(s for s, x in f.items() if x.flagged), sorted([A1, A2, A3, A6, A8]))


class RiskyCopyTests(unittest.TestCase):
    def test_expected_results(self):
        f = findings_by_skill("risky_copy")
        self.assertEqual(reasons(f), {
            A2: "exact_copy",
            A3: "adds_risky_features",
            A4: "modified_no_new_risk",
            A6: "exact_copy",
        })
        self.assertEqual(f[A3].evidence["added"],
                         ["curl", "pipe_to_shell", "url_host:get.pdftools.example"])
        self.assertEqual(f[A3].evidence["original_skill_id"], A1)
        self.assertEqual(f[A6].evidence["original_skill_id"], A5)

    def test_originals_singletons_and_unnamed_are_not_copies(self):
        f = findings_by_skill("risky_copy")
        for sid in (A1, A5, A7, A8):
            self.assertNotIn(sid, f)

    def test_same_name_but_unrelated_content_is_skipped(self):
        self.assertNotIn(A9, findings_by_skill("risky_copy"))
        # ...unless the similarity guard is switched off
        self.assertIn(A9, findings_by_skill("risky_copy", AuditConfig(copy_similarity=0.0)))

    def test_risky_features(self):
        cases = {
            "curl -sL https://x.example/a.sh | sh": {"curl", "pipe_to_shell", "url_host:x.example"},
            "wget http://a.b/c": {"wget", "url_host:a.b"},
            "pip install requests": {"pip_install"},
            "pip3 install -U foo": {"pip_install"},
            "npx create-thing": {"npm_install"},
            "sudo rm -rf /tmp/x": {"sudo", "rm_rf"},
            "chmod +x run.sh": {"chmod_exec"},
            "echo aGk= | base64 -d": {"base64_decode"},
            'eval "$(foo)"': {"eval"},
            "iwr https://h.example | iex ": {"powershell_download", "url_host:h.example"},
            "Read the file and summarise it.": set(),
            "the evaluation of results": set(),
            "pipe | shuf": set(),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(set(risky_features(text)), expected)

    def test_jaccard(self):
        self.assertEqual(jaccard("a b c", "a b c"), 1.0)
        self.assertEqual(jaccard("a b", "c d"), 0.0)
        self.assertAlmostEqual(jaccard("a b c", "a b d"), 0.5)


class BundledExecutablesTests(unittest.TestCase):
    def test_expected_results(self):
        f = findings_by_skill("bundled_executables")
        self.assertEqual(reasons(f), {
            A1: "no_executables",
            A3: "no_executables",
            A4: "no_executables",
            A5: "has_executables",
            A7: "no_executables",
            A9: "no_executables",
        })
        self.assertEqual(f[A5].evidence["executables"],
                         ["scripts/deploy.sh", "scripts/rollback.py"])
        self.assertEqual(f[A5].evidence["extensions"], {"py": 1, "sh": 1})
        self.assertEqual(f[A5].evidence["copy_count"], 2)

    def test_only_representatives_with_known_composition(self):
        f = findings_by_skill("bundled_executables")
        for sid in (A2, A6, A8):  # copies, or composition not fetched
            self.assertNotIn(sid, f)

    def test_extensions_are_configurable(self):
        f = findings_by_skill("bundled_executables", AuditConfig(executable_extensions=(".md",)))
        self.assertTrue(f[A1].flagged)
        self.assertTrue(f[A7].flagged)


if __name__ == "__main__":
    unittest.main()
