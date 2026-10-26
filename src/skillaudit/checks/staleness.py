"""E1: skills left unchanged while the project around them keeps moving.

Flag: the SKILL.md's last commit is at least ``stale_days`` before ``as_of``
AND the repository was pushed within the last ``active_days``.
Not applicable: no commit history for this file (only a subset of the dataset
has it) or no repository push date.
"""

from __future__ import annotations

from typing import Iterable

from skillaudit.checks.base import Check, Finding
from skillaudit.checks.base import register_check
from skillaudit.parsing import Skill


@register_check
class StalenessCheck(Check):
    name = "staleness"
    description = "Skill not updated in N days while its repository is still active"
    question = "E1"

    def run(self, skill: Skill) -> Iterable[Finding]:
        if not skill.history_known or skill.last_commit_at is None:
            return []
        if skill.repo_pushed_at is None:
            return []

        as_of = self.corpus.as_of
        skill_age = (as_of - skill.last_commit_at).days
        repo_age = (as_of - skill.repo_pushed_at).days
        stale = skill_age >= self.config.stale_days
        active = repo_age <= self.config.active_days

        if stale and active:
            reason = "stale"
        elif stale:
            reason = "repo_inactive"
        else:
            reason = "recently_updated"

        return [self.finding(
            skill, stale and active, reason,
            skill_age_days=skill_age,
            repo_push_age_days=repo_age,
            commit_count=skill.commit_count,
        )]
