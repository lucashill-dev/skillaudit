"""Shared test setup: puts src/ on the path and builds corpora from the fixtures."""

import sys
from pathlib import Path
from typing import Dict, Optional

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Built by tests/fixtures/make_fixtures.py; same schema as the official release.
FIXTURE_DB = Path(__file__).resolve().parent / "fixtures" / "sample.db"


def fixture_corpus(config=None):
    from skillaudit.config import AuditConfig
    from skillaudit.data import Dataset
    from skillaudit.parsing import build_corpus
    return build_corpus(Dataset(FIXTURE_DB), config or AuditConfig())


def findings_by_skill(check_name: str, config=None) -> Dict[str, object]:
    """Run one check on the fixtures; return {skill_id: Finding}."""
    from skillaudit.checks.base import create_checks
    from skillaudit.config import AuditConfig
    from skillaudit.runner import run_checks
    config = config or AuditConfig()
    out = {}
    for f in run_checks(create_checks([check_name]), fixture_corpus(config), config):
        assert f.skill_id not in out, f"two findings for {f.skill_id}"
        out[f.skill_id] = f
    return out
