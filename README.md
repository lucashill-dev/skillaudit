# SkillAudit

Static audit of AI agent skills (`SKILL.md` folders) in the GitSkills dataset
from the MSR 2027 Mining Challenge. Software Architecture group project: Lucas
Hill, Justin Mehl, Mahroush Chowdhury.

| Check | Question | Flags a skill when... |
|---|---|---|
| `staleness` | E1 | its SKILL.md is unchanged for 180+ days while the repo was pushed in the last 90 |
| `risky_copy` | E2 | it is a modified copy that adds commands (`curl`, `eval`, `pip install`, `\| sh`, ...) or URLs the original lacks |
| `bundled_executables` | E3 | its folder ships `.sh`, `.py`, `.js`, ... files (with how often that content is copied) |

The architecture question (Q1–Q4) compares this **layered plug-in** version
with the **single-script baseline** in `baseline/`.

## Setup

Python 3.10+. The tool itself uses only the standard library; matplotlib is
needed for charts and pytest for the tests.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,charts]"
```

## Run

```bash
# demo on the tiny fixture database
skillaudit run --data tests/fixtures/sample.db --out runs/fixtures

# the official challenge sample (87 MB download -> data/agent_skills_sample.db)
python scripts/fetch_sample.py
skillaudit run --data data/agent_skills_sample.db --out runs/sample-1
skillaudit charts runs/sample-1

# the baseline (same result files)
python baseline/skillaudit_single.py --data data/agent_skills_sample.db --out runs/baseline-1

# options
skillaudit run --data DB --out DIR --checks staleness,risky_copy \
    --stale-days 365 --active-days 30 --as-of 2026-07-31
skillaudit list-checks
```

`--data` takes the official GitSkills SQLite file (or the folder holding it):
the 277 MB sample, or the 41 GB full dataset from
[Zenodo](https://doi.org/10.5281/zenodo.21875637). It is opened read-only.

### Outputs

| File | Contents |
|---|---|
| `findings.csv` | one row per (check, skill): `flagged`, `reason`, JSON `evidence` |
| `summary.csv` | per check: evaluated, flagged, % flagged (the E1–E3 numbers), count per reason |
| `manifest.json` | config, dataset hash, git commit, output hashes, timings, peak memory |

Skills a check does not apply to (e.g. no commit history for staleness) get no
row for that check, so they are not in its denominator.

## How the code is organised

Four layers; each only uses the ones below it.

| Layer | File(s) | Job |
|---|---|---|
| Reporting | `src/skillaudit/reporting.py` | write `findings.csv`, `summary.csv`, `manifest.json`, charts |
| Checks | `src/skillaudit/checks/` | one file per check, plus `base.py` (the interface, and the registry that finds checks automatically) |
| Parsing | `src/skillaudit/parsing.py` | turn database rows into `Skill` objects and a `Corpus` (copy counts, text lookup) |
| Data | `src/skillaudit/data.py` | open the SQLite file and read only the needed columns |

`runner.py` connects the layers, `cli.py` is the command line, and `config.py`
holds every threshold (recorded in the manifest). Checks never see the database
(`tests/test_check_interface.py` enforces this).

### Every file

| File | What it is for |
|---|---|
| `README.md` | this guide |
| `pyproject.toml` | package metadata; installs the `skillaudit` command and optional extras (charts, tests) |
| `.gitignore` | keeps `.venv/`, `data/` (the dataset) and `runs/` (results) out of git |
| `src/skillaudit/__init__.py` | package marker and version; summarises the layers |
| `src/skillaudit/cli.py` | the `skillaudit` command: `run`, `list-checks`, `charts` |
| `src/skillaudit/config.py` | every threshold (stale days, similarity cut-off, executable extensions); recorded in each run's manifest |
| `src/skillaudit/runner.py` | runs one audit: data -> parsing -> checks -> reporting, and times each step |
| `src/skillaudit/data.py` | **data layer**: opens the SQLite file read-only, reads only the needed columns |
| `src/skillaudit/parsing.py` | **parsing layer**: rows -> `Skill` objects; `Corpus` answers copy counts and text lookups |
| `src/skillaudit/checks/__init__.py` | **checks layer** entry point; re-exports the interface |
| `src/skillaudit/checks/base.py` | the `Check` interface, the `Finding` result type, and the registry that discovers checks |
| `src/skillaudit/checks/staleness.py` | E1 check |
| `src/skillaudit/checks/risky_copy.py` | E2 check, including how copies are grouped |
| `src/skillaudit/checks/bundled_executables.py` | E3 check |
| `src/skillaudit/reporting.py` | **reporting layer**: `findings.csv`, `summary.csv`, `manifest.json`, charts |
| `baseline/skillaudit_single.py` | the same three checks in one script, for the Q1 comparison |
| `scripts/fetch_sample.py` | downloads the official challenge sample into `data/` |
| `scripts/compare_runs.py` | compares result hashes, run time and memory across runs (Q2, Q4) |
| `tests/__init__.py` | shared test setup (paths, helpers that build a corpus from the fixtures) |
| `tests/fixtures/make_fixtures.py` | builds `sample.db`; each of its 9 skills is designed to hit one branch of one check |
| `tests/fixtures/sample.db` | the tiny fixture database (same schema as the real one) |
| `tests/test_data_and_parsing.py` | tests for the data and parsing layers |
| `tests/test_checks.py` | expected results of each check on the fixtures |
| `tests/test_check_interface.py` | rules every check must follow, incl. "checks never touch the data layer" |
| `tests/test_end_to_end.py` | whole runs: CLI, identical repeated runs (Q2), baseline gives identical results |
| `docs/adding-a-check.md` | how to add a check, and what to record for Q1 |
| `docs/phase2-changes.md` | what changed since the Phase 1 proposal and why, plus first results (for the Phase 2 report) |

## Tests

```bash
pytest
```

They check each check's expected results, the plug-in contract, that checks
never touch the data layer, that repeated runs are byte-identical (Q2), and
that the baseline produces identical results.

## Reproducibility and performance (Q2, Q4)

```bash
skillaudit run --data data/agent_skills_sample.db --out runs/$(whoami)-1
skillaudit run --data data/agent_skills_sample.db --out runs/$(whoami)-2
python scripts/compare_runs.py runs/*     # exit 1 if results differ
```

Copy each other's `runs/` folders (not committed) to compare across laptops.
