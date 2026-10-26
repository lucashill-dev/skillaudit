"""Wires the layers together: data -> parsing -> checks -> reporting."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from skillaudit import __version__
from skillaudit.checks.base import Check, Finding
from skillaudit.checks.base import create_checks
from skillaudit.config import AuditConfig
from skillaudit.data import Dataset
from skillaudit.parsing import Corpus, build_corpus
from skillaudit.reporting import (
    FINDINGS_FILE,
    SUMMARY_FILE,
    summarise,
    write_findings,
    write_manifest,
    write_summary,
)


@dataclass
class RunResult:
    out_dir: Path
    findings: List[Finding]
    summary: List[Dict]
    timings: Dict[str, float]
    manifest_path: Path


def run_checks(checks: List[Check], corpus: Corpus, config: AuditConfig) -> List[Finding]:
    for check in checks:
        check.prepare(corpus, config)
    findings: List[Finding] = []
    for skill in corpus.skills:
        for check in checks:
            for f in check.run(skill):
                if f.check != check.name:
                    raise ValueError(f"check '{check.name}' returned a finding "
                                     f"labelled '{f.check}'")
                findings.append(f)
    return findings


def run_audit(data, out_dir, config: Optional[AuditConfig] = None,
              check_names: Optional[Iterable[str]] = None) -> RunResult:
    config = config or AuditConfig()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timings: Dict[str, float] = {}
    start = time.perf_counter()

    t = time.perf_counter()
    dataset = Dataset(data)
    corpus = build_corpus(dataset, config)
    timings["load_and_parse"] = time.perf_counter() - t

    t = time.perf_counter()
    checks = create_checks(check_names)
    findings = run_checks(checks, corpus, config)
    timings["checks"] = time.perf_counter() - t

    t = time.perf_counter()
    names = [c.name for c in checks]
    summary = summarise(findings, names)
    write_findings(out_dir / FINDINGS_FILE, findings)
    write_summary(out_dir / SUMMARY_FILE, summary)
    timings["report"] = time.perf_counter() - t
    timings["total"] = time.perf_counter() - start

    manifest = write_manifest(
        out_dir,
        implementation="layered",
        version=__version__,
        config=config.to_dict(),
        dataset=dataset.describe(),
        checks=names,
        as_of=corpus.as_of.isoformat(),
        counts={"skills": len(corpus), "findings": len(findings)},
        timings=timings,
    )
    return RunResult(out_dir, findings, summary, timings, manifest)
