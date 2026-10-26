"""Data layer (reading the SQLite file) and parsing layer (rows -> Skill objects)."""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests import FIXTURE_DB, fixture_corpus

from skillaudit.config import AuditConfig
from skillaudit.data import TABLE_COLUMNS, Dataset, DataError
from skillaudit.parsing import SiblingFile, parse_time, skill_folder

PDF = "alpha/webapp:.claude/skills/pdf-tools/SKILL.md"
DEPLOY = "epsilon/infra:.claude/skills/deploy-helper/SKILL.md"


class DataLayerTests(unittest.TestCase):
    def test_rows_are_projected_to_declared_columns(self):
        ds = Dataset(FIXTURE_DB)
        for table, cols in TABLE_COLUMNS.items():
            for row in ds.rows(table):
                self.assertEqual(tuple(row.keys()), cols)

    def test_accepts_file_or_folder(self):
        self.assertEqual(Dataset(FIXTURE_DB.parent).path, FIXTURE_DB)

    def test_missing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DataError):
                Dataset(tmp)

    def test_database_is_opened_read_only(self):
        with self.assertRaises(sqlite3.OperationalError):
            Dataset(FIXTURE_DB).con.execute("DELETE FROM repos")

    def test_describe_hashes_database(self):
        info = Dataset(FIXTURE_DB).describe()
        self.assertEqual(info["file"], "sample.db")
        self.assertEqual(len(info["sha256"]), 64)


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.corpus = fixture_corpus()

    def test_duplicates_and_malformed_rows_are_dropped(self):
        self.assertEqual(len(self.corpus), 9)

    def test_as_of_defaults_to_latest_discovery(self):
        self.assertEqual(self.corpus.as_of, datetime(2026, 7, 31, tzinfo=timezone.utc))

    def test_as_of_override(self):
        c = fixture_corpus(AuditConfig(as_of="2026-01-01"))
        self.assertEqual(c.as_of, datetime(2026, 1, 1, tzinfo=timezone.utc))

    def test_copies_share_content_lookup(self):
        pdf = next(s for s in self.corpus.skills if s.skill_id == PDF)
        self.assertEqual(self.corpus.copy_count(pdf.file_sha), 2)
        copy = next(s for s in self.corpus.skills if s.repo_full_name == "beta/site")
        self.assertIsNone(copy.content)
        self.assertIsNotNone(self.corpus.content_for(copy.file_sha))

    def test_siblings_attach_whether_path_is_file_or_folder(self):
        by_id = {s.skill_id: s for s in self.corpus.skills}
        self.assertEqual([f.name for f in by_id[PDF].siblings], ["forms.md"])
        self.assertEqual(len(by_id[DEPLOY].siblings), 4)

    def test_history_fields_ignored_when_not_fetched(self):
        s = next(s for s in self.corpus.skills if s.repo_full_name == "delta/notes")
        self.assertFalse(s.history_known)
        self.assertIsNone(s.last_commit_at)

    def test_copies_inherit_the_representatives_name(self):
        # The release parses front matter only on representatives.
        copy = next(s for s in self.corpus.skills if s.repo_full_name == "beta/site")
        self.assertEqual(copy.name, "pdf-tools")

    def test_names_are_normalised(self):
        self.assertIn("pdf-tools", self.corpus.names())


class ValueParsingTests(unittest.TestCase):
    def test_parse_time_variants(self):
        utc = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(parse_time("2026-07-01T12:00:00Z"), utc)
        self.assertEqual(parse_time("2026-07-01T12:00:00+00:00"), utc)
        self.assertEqual(parse_time("2026-07-01T14:00:00+02:00"), utc)
        self.assertEqual(parse_time("2026-07-01T12:00:00"), utc)
        self.assertIsNone(parse_time("not a date"))
        self.assertIsNone(parse_time(None))

    def test_skill_folder(self):
        self.assertEqual(skill_folder("a/b/SKILL.md"), "a/b")
        self.assertEqual(skill_folder("a/b/skill.md"), "a/b")
        self.assertEqual(skill_folder("a/b/"), "a/b")
        self.assertEqual(skill_folder("SKILL.md"), "")

    def test_sibling_extension(self):
        self.assertEqual(SiblingFile("scripts/run.SH", "file").extension, ".sh")
        self.assertEqual(SiblingFile(".env", "file").extension, "")
        self.assertEqual(SiblingFile("Makefile", "file").extension, "")


if __name__ == "__main__":
    unittest.main()
