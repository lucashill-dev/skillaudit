"""E3: skills that ship executable files, and how widely they are copied.

Evaluated once per distinct content (the dataset's representative occurrence,
which is the only one with a recorded folder listing). Flag: at least one
bundled file has an executable extension. Evidence includes how many
occurrences share this exact content, so E3's "how widely copied" can be
computed from the findings file.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from skillaudit.checks.base import Check, Finding
from skillaudit.checks.base import register_check
from skillaudit.parsing import Skill

MAX_LISTED = 20


@register_check
class BundledExecutablesCheck(Check):
    name = "bundled_executables"
    description = "Skill folder contains scripts or binaries"
    question = "E3"

    def run(self, skill: Skill) -> Iterable[Finding]:
        if not skill.is_primary or not skill.composition_known:
            return []

        exts = {e.lower() for e in self.config.executable_extensions}
        executables = sorted(f.name for f in skill.siblings
                             if f.entry_type == "file" and f.extension in exts)
        by_ext = Counter(f.rsplit(".", 1)[-1].lower() for f in executables)

        return [self.finding(
            skill, bool(executables),
            "has_executables" if executables else "no_executables",
            executable_count=len(executables),
            executables=executables[:MAX_LISTED],
            extensions=dict(sorted(by_ext.items())),
            copy_count=self.corpus.copy_count(skill.file_sha),
        )]
