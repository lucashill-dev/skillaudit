# Phase 2: changes since the Phase 1 proposal

Notes for the "revised plan / changes since Phase 1" section of the Phase 2
report. Each item says what changed and why.

## 1. Data source: official SQLite release instead of DuckDB + Parquet

**Phase 1:** Python, DuckDB, and the dataset's Parquet files.

**Now:** SkillAudit reads the official GitSkills SQLite file with Python's
built-in `sqlite3` module, opened read-only. Development uses the authors'
official sample (`agent_skills_sample.db`, 277 MB; downloaded by
`scripts/fetch_sample.py`). The full dataset is the same format (41 GB, Zenodo
DOI 10.5281/zenodo.21875637).

**Why:**
- The challenge distributes the dataset as one SQLite file; the Parquet files
  are a mirror on Hugging Face. Using the primary release is simpler to cite and
  reproduce.
- Querying the Hugging Face mirror remotely was rate-limited (HTTP 429) for
  anonymous users, so it was not a dependable way to get data.
- The official sample is drawn deterministically (the 13,000 distinct contents
  with the lowest hashes) and includes *every* copy of each sampled skill, so
  the copy-based checks (E2, E3) behave on it exactly as on the full dataset.
  A sample we drew ourselves would have broken copy groups.
- DuckDB is no longer needed, so the tool has no third-party dependencies
  (matplotlib is optional, for charts). This removed an installation problem
  we hit (DuckDB needing `pytz` for timestamps).

**Consequence for Q4:** "only load the columns we need" still applies: the data
layer selects 12 of the 30 `artifacts` columns, and never loads the bundled
files' contents. Whether this is fast enough for the 41 GB file is the Phase 3
Q4 measurement.

*Suggested ADR:* data management (SQLite vs. Parquet/DuckDB vs. a self-drawn sample).

## 2. Simplified the prototype

While building the prototype we first supported three input formats (SQLite,
Parquet via DuckDB, JSON test files) and a `--repo-limit` option for cutting
down the 44 GB Parquet files. Once we settled on the official SQLite sample,
we removed:

- the DuckDB/Parquet reader and the JSON-lines reader (one reader remains);
- `--repo-limit` (the official sample already gives a small, complete subset);
- unused fields on the `Skill` and `Repo` objects, and the columns that fed them;
- a separate `reasons.csv` output (its counts are now a column of `summary.csv`).

Each layer is now one module (`data.py`, `parsing.py`, `reporting.py`) except
`checks/`, which stays a package because each check is its own plug-in file.
The test fixtures are a tiny SQLite database with the real schema, so tests run
through the same code path as real runs.

**Why it matters for the architecture question:** fewer moving parts make the
Q1 comparison fairer. The layered version's extra structure is now only the
layers and the plug-in mechanism we are actually evaluating, not speculative
input options.

## 3. Definitions made concrete

The proposal described the checks informally. The prototype fixes them as
follows (all thresholds are in `config.py`, can be changed on the command line,
and are recorded in each run's manifest):

**Reference date.** Ages are measured from the latest `discovered_at` in the
data (the snapshot date), not today's date, so results depend only on the data.

**E1, staleness.** Flagged if the SKILL.md's last commit is at least 180 days
before the reference date *and* the repository was pushed within the last 90
days. Only evaluated for skills with commit history. The dataset collected
history for a subset only (458,548 of 3.8M occurrences; 3,010 in the official
sample), so E1 percentages are over that subset. Cut-offs can be varied with
`--stale-days` / `--active-days` (the Phase 1 risk "stale is hard to define").

**E2, risky copies.** How copies are grouped:
1. Occurrences with the same front-matter `name` form a group.
2. The *original* is the content whose earliest occurrence has the earliest
   first commit (ties: most copies, then hash).
3. Other occurrences with identical content are exact copies (never flagged).
4. Other contents are modified copies, but only if their word overlap
   (Jaccard similarity) with the original is at least 0.5. Below that, they are
   treated as unrelated skills that share a generic name (e.g. "helper") and
   are left out.

Copies inherit the `name` of their content's representative. The release
parses front matter only on the representative (16,772 of the sample's 16,786
copies have no `name` of their own); without this, almost every copy was
skipped. We found this from the first run on the sample, where only 200
occurrences were evaluated.

A modified copy is flagged if it contains a risky feature the original lacks:
`curl`, `wget`, piping into a shell, `eval`, `exec(`, `pip install`,
`npm install`/`npx`, `sudo`, `rm -rf`, `chmod +x`, `base64 -d`, PowerShell
download commands, or a URL to a host the original does not mention.

*Suggested ADR:* copy grouping (by name + similarity vs. exact hash only vs.
near-duplicate hashing). Known limitation for Q3: copies that were renamed are
missed, and grouping by name depends on the 0.5 threshold.

**E3, bundled executables.** Evaluated once per distinct content (the
dataset's representative, the only occurrence with a recorded folder listing).
Flagged if any bundled file has an executable extension (`.sh`, `.py`, `.js`,
`.ts`, `.rb`, `.ps1`, `.bat`, `.exe`, `.jar`, ... full list in `config.py`).
The finding records how many occurrences share that exact content, for the
"how widely copied" part of E3.

**Denominators.** A check that does not apply to a skill (no history for E1,
not a copy for E2, no folder listing for E3) writes no row for it, so
`summary.csv` percentages are over the skills each check could evaluate.

## 4. Architecture as built

- **Layers:** data → parsing → checks → reporting, as proposed. Dependencies
  point only downward; a test fails if a check imports the data layer.
- **Check interface:** `prepare(corpus, config)` once, then `run(skill)` →
  findings. Checks get `Skill` objects and a read-only `Corpus`, never rows.
- **Plug-in discovery:** a check registers itself with `@register_check`;
  adding a check is adding one file (see `docs/adding-a-check.md`, which is
  also the Q1 measurement protocol).
- **Baseline:** `baseline/skillaudit_single.py` implements the same checks in
  one script. A test requires both versions to produce byte-identical
  `findings.csv` and `summary.csv`, as Phase 1 required before comparing them.
- **Reproducibility (Q2):** outputs are written in a canonical order with no
  timestamps; `manifest.json` records the dataset hash, git commit, config and
  output hashes. `scripts/compare_runs.py` checks hashes across runs and laptops.
- **Performance (Q4):** each run records load, check and report times and peak
  memory in `manifest.json`.

*Suggested ADRs:* decomposition (layers + plug-ins vs. one script); check
interface and dependency direction; static analysis only (never executing
skills) as a security decision; reproducibility (canonical outputs + manifest).

## 5. Status and preliminary results

Tested on a 9-skill fixture database built to hit every branch of every check,
on macOS (Python 3.14) and Linux (Python 3.10).

**First run on the official sample** (29,786 occurrences, 2026-10-26, after
the copy-name fix in section 3):

| Check | Evaluated | Flagged | % |
|---|---:|---:|---:|
| E1 staleness | 3,010 | 31 | 1.03 |
| E2 risky_copy | 15,439 | 71 | 0.46 |
| E3 bundled_executables | 12,990 | 1,387 | 10.68 |

- **E2 breakdown:** of the 15,439 copies, 14,994 are exact copies (never
  flagged) and 445 are modified copies, of which 71 (16%) add a risky feature.
  The most common additions are new URL hosts (38), piping into a shell (21) and
  `npm install`/`npx` (15). We need to decide whether to report E2 over all
  copies (0.46%) or over modified copies only (16%); the latter matches the
  question better. Q3 hand-labelling should check how many of the 71 are real.
- **E1 coverage:** staleness can only be evaluated for the 3,010 occurrences with
  commit history (10% of the sample; the dataset collected history only for
  representatives, on a subset).
- **Q2:** `findings.csv` and `summary.csv` were byte-identical between a MacBook
  (arm64, Python 3.14) and a Linux machine (Python 3.10), and between the
  layered version and the baseline.
- **Q4 (sample):** about 2.5–4.5 s total and 260–280 MB peak memory, depending on
  the machine. The full dataset is about 150x larger; whether memory scales
  acceptably is the Phase 3 measurement.

Open items:
- Q3 (precision/recall on 100 hand-labelled skills) not started.
- Q1 (adding a new check to both versions) is Phase 3 work, following
  `docs/adding-a-check.md`.
- Full-dataset run (41 GB) for Q4.
