"""The check plug-in interface and registry: the central architectural boundary.

A check:
  * declares a unique ``name``, a ``description`` and the research question it
    answers (``question``, e.g. "E1");
  * gets the Corpus and config once in ``prepare`` (for corpus-wide work such as
    grouping copies);
  * returns zero or more Findings per Skill from ``run``.

Returning no finding means "not applicable" (the skill is left out of that
check's denominator). Returning a Finding with ``flagged=False`` means "checked,
no problem". Checks must not import ``skillaudit.data`` or do any I/O.

Adding a check = adding one module to ``skillaudit/checks/`` with a class
decorated by ``@register_check``. Nothing else (runner, CLI, reporting) has to
change; that is what Q1 measures against the single-script baseline.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Dict, Iterable, List, Mapping, Optional, Type

from skillaudit.config import AuditConfig
from skillaudit.parsing import Corpus, Skill


@dataclass(frozen=True)
class Finding:
    check: str
    skill_id: str
    file_sha: str
    flagged: bool
    reason: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def evidence_json(self) -> str:
        """Canonical JSON so output files are byte-identical across runs."""
        return json.dumps(self.evidence, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, default=str)


class Check(ABC):
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    question: ClassVar[str] = ""

    def __init__(self) -> None:
        self.corpus: Corpus | None = None
        self.config: AuditConfig = AuditConfig()

    def prepare(self, corpus: Corpus, config: AuditConfig) -> None:
        """Called once before ``run``. Override to precompute corpus-wide data,
        but call ``super().prepare(...)``."""
        self.corpus = corpus
        self.config = config

    @abstractmethod
    def run(self, skill: Skill) -> Iterable[Finding]:
        """Evaluate one skill occurrence."""

    # Helper so checks build findings consistently.
    def finding(self, skill: Skill, flagged: bool, reason: str, **evidence) -> Finding:
        return Finding(
            check=self.name,
            skill_id=skill.skill_id,
            file_sha=skill.file_sha,
            flagged=bool(flagged),
            reason=reason,
            evidence=evidence,
        )


# ------------------------------------------------------------------ registry
_REGISTRY: Dict[str, Type[Check]] = {}
_DISCOVERED = False

# Modules in this package that are infrastructure, not checks.
_SKIP_MODULES = {"base"}


def register_check(cls: Type[Check]) -> Type[Check]:
    if not cls.name:
        raise TypeError(f"{cls.__name__} must define a non-empty 'name'")
    existing = _REGISTRY.get(cls.name)
    if existing is not None and existing is not cls:
        raise ValueError(f"duplicate check name '{cls.name}' "
                         f"({existing.__name__} and {cls.__name__})")
    _REGISTRY[cls.name] = cls
    return cls


def unregister_check(name: str) -> None:
    """Used by tests that register temporary checks."""
    _REGISTRY.pop(name, None)


def discover() -> None:
    """Import every module in skillaudit.checks so their decorators run."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    import skillaudit.checks as pkg

    for mod in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if mod.name not in _SKIP_MODULES and not mod.name.startswith("_"):
            importlib.import_module(f"{pkg.__name__}.{mod.name}")
    _DISCOVERED = True


def available_checks() -> List[Type[Check]]:
    discover()
    return [_REGISTRY[n] for n in sorted(_REGISTRY)]


def create_checks(names: Optional[Iterable[str]] = None) -> List[Check]:
    """Instantiate the requested checks (all of them by default), sorted by name."""
    discover()
    if names is None:
        selected = sorted(_REGISTRY)
    else:
        selected = sorted(set(names))
        unknown = [n for n in selected if n not in _REGISTRY]
        if unknown:
            raise KeyError(f"unknown check(s): {', '.join(unknown)}; "
                           f"available: {', '.join(sorted(_REGISTRY))}")
    return [_REGISTRY[n]() for n in selected]
