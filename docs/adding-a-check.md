# Adding a check (and measuring it for Q1)

## Layered version

1. Create `src/skillaudit/checks/<your_check>.py`:

   ```python
   from skillaudit.checks.base import Check, register_check


   @register_check
   class MyCheck(Check):
       name = "my_check"
       description = "One line describing what gets flagged"
       question = "E4"

       def prepare(self, corpus, config):   # optional, for corpus-wide work
           super().prepare(corpus, config)

       def run(self, skill):
           if not applicable(skill):
               return []                      # left out of the denominator
           return [self.finding(skill, flagged, "reason_code", some_evidence=1)]
   ```

2. Add any thresholds to `AuditConfig` in `config.py` (and a CLI flag if needed).
3. If the check needs a dataset column that is not loaded yet, add it to
   `TABLE_COLUMNS` in `data.py` and to `Skill` in `parsing.py`. (Record this
   for Q1: it is the main way a new check can reach below its own layer.)
4. Add fixture rows in `tests/fixtures/make_fixtures.py`, re-run it to rebuild
   `sample.db`, and add expected results in `tests/test_checks.py`. The
   contract tests pick the check up automatically. Update the check list in
   `test_the_three_phase1_checks_are_discovered`.

Nothing in `runner.py`, `cli.py` or `reporting.py` should need to change.

## Baseline version

Add the logic inside the main loop of `baseline/skillaudit_single.py`, add
its name to the `checks` list used for `summary.csv`, and add any constants at
the top of the file.

## What to record (Q1)

Do the same new check in both versions, starting from the same commit, in
separate branches. For each version, record:

| Metric | How |
|---|---|
| Lines of existing code changed | `git diff --stat main -- . ':!tests'`, counting only modified or deleted lines in files that already existed |
| Files touched | `git diff --name-only main` |
| Tests broken | run the test suite **before** fixing anything; count failures |
| Time spent | wall-clock minutes, logged by the person doing the change |

Then confirm that both versions still produce identical outputs
(`scripts/compare_runs.py`).
