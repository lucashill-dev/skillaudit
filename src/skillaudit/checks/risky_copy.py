"""E2: modified copies that add command execution or network access.

How copies are grouped (see ADR on copy grouping):
  1. Occurrences with the same front-matter ``name`` form a lineage.
  2. Within a lineage, the *original* content is the one whose earliest
     occurrence has the earliest first commit (ties: most occurrences, then
     hash). Its earliest occurrence is the original itself and is not judged.
  3. Other occurrences of the original content are exact copies (never flagged).
  4. Other contents are modified copies, but only if their word-set Jaccard
     similarity to the original is >= ``copy_similarity``; below that they are
     treated as unrelated skills that happen to share a name (not applicable).

Flag: a modified copy contains a risky feature (command or network host) that
the original does not.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

from skillaudit.checks.base import Check, Finding
from skillaudit.checks.base import register_check
from skillaudit.config import AuditConfig
from skillaudit.parsing import Corpus, Skill

RISKY_PATTERNS: Dict[str, re.Pattern] = {
    "curl": re.compile(r"\bcurl\s"),
    "wget": re.compile(r"\bwget\s"),
    "pipe_to_shell": re.compile(r"\|\s*(?:sudo\s+)?(?:ba|z)?sh\b"),
    "eval": re.compile(r"\beval\s*[\(\s\"'`$]"),
    "exec": re.compile(r"\bexec\s*\("),
    "pip_install": re.compile(r"\bpip3?\s+install\b"),
    "npm_install": re.compile(r"\bnpm\s+(?:install|i)\b|\bnpx\s"),
    "sudo": re.compile(r"\bsudo\s"),
    "rm_rf": re.compile(r"\brm\s+-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\b"),
    "chmod_exec": re.compile(r"\bchmod\s+(?:[ugoa]*\+x|0?7[0-7]{2})\b"),
    "base64_decode": re.compile(r"\bbase64\s+(?:-d|--decode|-D)\b"),
    "powershell_download": re.compile(
        r"(?i)\binvoke-webrequest\b|\biwr\s|\bdownloadstring\b|\binvoke-expression\b|\biex\s"),
}
URL_HOST = re.compile(r"https?://([A-Za-z0-9.-]+)")
WORD = re.compile(r"[a-z0-9_]+")


def risky_features(text: str) -> FrozenSet[str]:
    found = {name for name, pat in RISKY_PATTERNS.items() if pat.search(text)}
    found |= {"url_host:" + h.lower().rstrip(".") for h in URL_HOST.findall(text)}
    return frozenset(found)


def jaccard(a: str, b: str) -> float:
    wa, wb = set(WORD.findall(a.lower())), set(WORD.findall(b.lower()))
    if not wa and not wb:
        return 1.0
    return len(wa & wb) / len(wa | wb)


def _first_commit_key(s: Skill) -> Tuple[int, str, str]:
    # Unknown history sorts after any known date.
    if s.first_commit_at is None:
        return (1, "", s.skill_id)
    return (0, s.first_commit_at.isoformat(), s.skill_id)


@register_check
class RiskyCopyCheck(Check):
    name = "risky_copy"
    description = "Modified copy adds commands or network hosts the original lacks"
    question = "E2"

    def prepare(self, corpus: Corpus, config: AuditConfig) -> None:
        super().prepare(corpus, config)
        # name -> (original sha, original occurrence id)
        self._origin: Dict[str, Tuple[str, str]] = {}
        self._features: Dict[str, FrozenSet[str]] = {}
        for name in corpus.names():
            occurrences = corpus.named(name)
            if len(occurrences) < 2:
                continue  # nothing was copied
            shas: Dict[str, List[Skill]] = {}
            for s in occurrences:
                shas.setdefault(s.file_sha, []).append(s)
            original_sha = min(
                shas,
                key=lambda sha: (min(_first_commit_key(s) for s in shas[sha]),
                                 -len(shas[sha]), sha),
            )
            first = min(shas[original_sha], key=_first_commit_key)
            self._origin[name] = (original_sha, first.skill_id)

    def _features_for(self, sha: str) -> Optional[FrozenSet[str]]:
        if sha not in self._features:
            text = self.corpus.content_for(sha)
            if text is None:
                return None
            self._features[sha] = risky_features(text)
        return self._features[sha]

    def run(self, skill: Skill) -> Iterable[Finding]:
        if not skill.name or skill.name not in self._origin:
            return []
        original_sha, original_id = self._origin[skill.name]
        if skill.skill_id == original_id:
            return []  # the original itself is not a copy

        if skill.file_sha == original_sha:
            return [self.finding(skill, False, "exact_copy",
                                 original_skill_id=original_id, added=[])]

        copy_text = self.corpus.content_for(skill.file_sha)
        original_text = self.corpus.content_for(original_sha)
        if copy_text is None or original_text is None:
            return []  # cannot compare without both texts

        similarity = jaccard(copy_text, original_text)
        if similarity < self.config.copy_similarity:
            return []  # different skill that shares a name

        added = sorted(self._features_for(skill.file_sha) - self._features_for(original_sha))
        return [self.finding(
            skill, bool(added),
            "adds_risky_features" if added else "modified_no_new_risk",
            original_skill_id=original_id,
            similarity=round(similarity, 4),
            added=added,
        )]
