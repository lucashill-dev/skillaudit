"""Command-line interface.

    skillaudit run --data agent_skills_sample.db --out runs/sample-1
    skillaudit list-checks
    skillaudit charts runs/sample-1
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from skillaudit import __version__
from skillaudit.config import AuditConfig


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skillaudit", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"skillaudit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="audit a GitSkills SQLite file")
    run.add_argument("--data", required=True, help="GitSkills .db file (or the folder holding it)")
    run.add_argument("--out", required=True, help="output folder for CSVs and manifest")
    run.add_argument("--checks", help="comma-separated check names (default: all)")
    run.add_argument("--as-of", help="reference date (default: latest discovered_at)")
    run.add_argument("--stale-days", type=int, default=AuditConfig.stale_days)
    run.add_argument("--active-days", type=int, default=AuditConfig.active_days)
    run.add_argument("--copy-similarity", type=float, default=AuditConfig.copy_similarity)

    sub.add_parser("list-checks", help="show available checks")

    charts = sub.add_parser("charts", help="draw charts for a finished run")
    charts.add_argument("run_dir")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "list-checks":
        from skillaudit.checks.base import available_checks
        for cls in available_checks():
            print(f"{cls.name:<22} {cls.question:<4} {cls.description}")
        return 0

    if args.command == "charts":
        from skillaudit.reporting import make_charts
        for path in make_charts(args.run_dir):
            print(path)
        return 0

    from skillaudit.runner import run_audit

    config = AuditConfig(as_of=args.as_of, stale_days=args.stale_days,
                         active_days=args.active_days, copy_similarity=args.copy_similarity)
    names = [n.strip() for n in args.checks.split(",") if n.strip()] if args.checks else None
    result = run_audit(args.data, args.out, config=config, check_names=names)

    print(f"{'check':<22}{'evaluated':>10}{'flagged':>9}{'%':>8}")
    for row in result.summary:
        print(f"{row['check']:<22}{row['evaluated']:>10}{row['flagged']:>9}"
              f"{row['pct_flagged']:>8}")
    print(f"\n{len(result.findings)} findings in {result.timings['total']:.2f}s "
          f"-> {result.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
