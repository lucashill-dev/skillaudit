"""Contract tests every registered check must pass, plus registry behaviour.

These run against every check automatically, so a new check gets them for
free (and a broken one fails here, not deep inside a run).
"""

import ast
import inspect
import unittest
from pathlib import Path

from tests import fixture_corpus

from skillaudit.checks.base import Check, Finding
from skillaudit.checks.base import (
    available_checks,
    create_checks,
    register_check,
    unregister_check,
)
from skillaudit.config import AuditConfig
from skillaudit.runner import run_checks


class ContractTests(unittest.TestCase):
    def test_the_three_phase1_checks_are_discovered(self):
        names = [c.name for c in available_checks()]
        self.assertEqual(names, ["bundled_executables", "risky_copy", "staleness"])

    def test_every_check_declares_metadata(self):
        for cls in available_checks():
            with self.subTest(check=cls.name):
                self.assertTrue(cls.name and cls.name == cls.name.lower())
                self.assertTrue(cls.description)
                self.assertRegex(cls.question, r"^[EQ]\d+$")

    def test_findings_are_well_formed_and_deterministic(self):
        config = AuditConfig()
        for cls in available_checks():
            with self.subTest(check=cls.name):
                first = run_checks([cls()], fixture_corpus(config), config)
                second = run_checks([cls()], fixture_corpus(config), config)
                self.assertEqual(first, second)
                self.assertTrue(first, "check produced no findings on the fixtures")
                for f in first:
                    self.assertIsInstance(f, Finding)
                    self.assertEqual(f.check, cls.name)
                    self.assertIsInstance(f.flagged, bool)
                    self.assertTrue(f.reason)
                    f.evidence_json()  # must be serialisable

    def test_checks_do_not_import_the_data_layer(self):
        """Layering rule: checks only see parsing-layer objects."""
        pkg = Path(inspect.getfile(Check)).parent
        for path in sorted(pkg.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                elif isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                for m in mods:
                    with self.subTest(file=path.name, module=m):
                        self.assertFalse(m.startswith("skillaudit.data"))
                        self.assertNotEqual(m, "sqlite3")


class RegistryTests(unittest.TestCase):
    def tearDown(self):
        unregister_check("test_always_flag")

    def test_new_check_plugs_in_without_touching_other_code(self):
        @register_check
        class AlwaysFlag(Check):
            name = "test_always_flag"
            description = "flags everything"
            question = "Q1"

            def run(self, skill):
                return [self.finding(skill, True, "always")]

        checks = create_checks(["test_always_flag"])
        corpus = fixture_corpus()
        findings = run_checks(checks, corpus, AuditConfig())
        self.assertEqual(len(findings), len(corpus))

    def test_duplicate_names_are_rejected(self):
        with self.assertRaises(ValueError):
            @register_check
            class Dupe(Check):
                name = "staleness"

                def run(self, skill):
                    return []

    def test_unknown_check_name(self):
        with self.assertRaises(KeyError):
            create_checks(["nope"])

    def test_mislabelled_finding_is_rejected(self):
        class Liar(Check):
            name = "liar"

            def run(self, skill):
                return [Finding("staleness", skill.skill_id, skill.file_sha, True, "x")]

        with self.assertRaises(ValueError):
            run_checks([Liar()], fixture_corpus(), AuditConfig())


if __name__ == "__main__":
    unittest.main()
