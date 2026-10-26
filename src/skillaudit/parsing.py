"""Parsing layer: turns database rows into Skill objects and a Corpus.

Checks only ever see these objects, never rows or the database. The Corpus
answers the corpus-wide questions checks need (how many copies of this content
exist? what is the text for this hash?).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from skillaudit.config import AuditConfig
from skillaudit.data import ARTIFACTS, REPOS, SIBLINGS, Dataset


# ------------------------------------------------------------------ objects
@dataclass(frozen=True)
class SiblingFile:
    """A file or folder stored next to a skill's SKILL.md."""

    name: str  # relative name, e.g. scripts/deploy.sh
    entry_type: str  # "file" or "dir"

    @property
    def extension(self) -> str:
        base = self.name.rsplit("/", 1)[-1]
        if "." not in base.lstrip("."):
            return ""
        return "." + base.rsplit(".", 1)[-1].lower()


@dataclass(frozen=True)
class Skill:
    """One SKILL.md occurrence (a repository + path)."""

    skill_id: str  # "<repo>:<path>"
    repo_full_name: str
    path: str
    file_sha: str  # content hash: equal hashes = exact copies
    name: Optional[str]  # front-matter name, lower-cased (copies inherit the representative's)
    content: Optional[str]  # text; the dataset stores it on the representative only
    is_primary: bool  # the dataset's one representative row for this content
    history_known: bool  # commit history was collected for this file
    composition_known: bool  # folder listing was collected for this file
    first_commit_at: Optional[datetime]
    last_commit_at: Optional[datetime]
    commit_count: Optional[int]
    repo_pushed_at: Optional[datetime]
    siblings: Tuple[SiblingFile, ...] = ()


class Corpus:
    def __init__(self, skills: Iterable[Skill], as_of: datetime):
        self.skills: List[Skill] = sorted(skills, key=lambda s: s.skill_id)
        self.as_of = as_of
        self._by_sha: Dict[str, List[Skill]] = defaultdict(list)
        self._by_name: Dict[str, List[Skill]] = defaultdict(list)
        self._content: Dict[str, str] = {}
        for s in self.skills:
            self._by_sha[s.file_sha].append(s)
            if s.name:
                self._by_name[s.name].append(s)
            if s.content is not None:
                self._content.setdefault(s.file_sha, s.content)

    def __len__(self) -> int:
        return len(self.skills)

    def copy_count(self, file_sha: str) -> int:
        """Occurrences with exactly this content."""
        return len(self._by_sha.get(file_sha, ()))

    def content_for(self, file_sha: str) -> Optional[str]:
        """SKILL.md text for a content hash (stored once per distinct content)."""
        return self._content.get(file_sha)

    def named(self, name: str) -> List[Skill]:
        return list(self._by_name.get(name, ()))

    def names(self) -> List[str]:
        return sorted(self._by_name)


# ------------------------------------------------------------------ values
def parse_time(value) -> Optional[datetime]:
    """ISO-8601 string (with 'Z' or an offset) -> aware UTC datetime, else None."""
    if value is None or value == "":
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _flag(value) -> bool:
    return str(value).strip().lower() in ("1", "true") if value is not None else False


def _int(value) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _name(value) -> Optional[str]:
    n = " ".join(str(value).strip().lower().split()) if value is not None else ""
    return n or None


def skill_folder(path: str) -> str:
    """'.claude/skills/x/SKILL.md' -> '.claude/skills/x' (siblings join on the folder)."""
    p = (path or "").rstrip("/")
    head, _, tail = p.rpartition("/")
    return head if tail.lower() == "skill.md" else p


# ------------------------------------------------------------------ build
def build_corpus(dataset: Dataset, config: AuditConfig) -> Corpus:
    pushed: Dict[str, Optional[datetime]] = {
        r["full_name"]: parse_time(r["pushed_at"])
        for r in dataset.rows(REPOS) if r["full_name"]
    }

    siblings: Dict[Tuple[str, str], List[SiblingFile]] = defaultdict(list)
    for r in dataset.rows(SIBLINGS):
        if r["repo_full_name"] and r["artifact_path"] is not None and r["entry_name"]:
            key = (r["repo_full_name"], skill_folder(str(r["artifact_path"])))
            siblings[key].append(SiblingFile(str(r["entry_name"]),
                                             str(r["entry_type"] or "file")))

    skills: List[Skill] = []
    seen = set()
    latest_discovery: Optional[datetime] = None
    for r in dataset.rows(ARTIFACTS):
        repo, path, sha = r["repo_full_name"], r["path"], r["file_sha"]
        if not repo or not path or not sha:
            continue  # cannot identify the occurrence
        skill_id = f"{repo}:{path}"
        if skill_id in seen:
            continue  # same file recorded by two collection runs
        seen.add(skill_id)

        discovered = parse_time(r["discovered_at"])
        if discovered and (latest_discovery is None or discovered > latest_discovery):
            latest_discovery = discovered

        history = _flag(r["history_fetched"])
        skills.append(Skill(
            skill_id=skill_id,
            repo_full_name=repo,
            path=str(path),
            file_sha=str(sha),
            name=_name(r["name"]),
            content=r["content"],
            is_primary=_flag(r["dedup_primary"]),
            history_known=history,
            composition_known=_flag(r["composition_fetched"]),
            first_commit_at=parse_time(r["first_commit_at"]) if history else None,
            last_commit_at=parse_time(r["last_commit_at"]) if history else None,
            commit_count=_int(r["commit_count"]) if history else None,
            repo_pushed_at=pushed.get(repo),
            siblings=tuple(sorted(siblings.get((repo, skill_folder(str(path))), ()),
                                  key=lambda f: f.name)),
        ))

    # The dataset parses front matter only for each content's representative.
    # Copies have identical bytes, so they share its name.
    name_by_sha = {s.file_sha: s.name for s in skills if s.name}
    skills = [replace(s, name=name_by_sha.get(s.file_sha)) if s.name is None else s
              for s in skills]

    # Ages are measured from the snapshot date, so results depend only on the data.
    as_of = parse_time(config.as_of) if config.as_of else latest_discovery
    if as_of is None:
        raise ValueError("cannot determine the snapshot date; pass --as-of")
    return Corpus(skills, as_of)
