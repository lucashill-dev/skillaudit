"""Run configuration shared by every layer.

Every threshold that affects results lives here so it is recorded in the run
manifest. Changing a value here (or on the command line) is how we test the
different "stale" cut-offs mentioned in the Phase 1 risk table.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass(frozen=True)
class AuditConfig:
    # Reference date for age calculations (ISO date/time). None = use the latest
    # `discovered_at` in the loaded data, so results depend only on the snapshot.
    as_of: Optional[str] = None

    # E1 staleness: skill unchanged for >= stale_days while its repo was pushed
    # within the last active_days.
    stale_days: int = 180
    active_days: int = 90

    # E2 risky copies: minimum word-set Jaccard similarity between a modified
    # copy and the original for them to count as the same skill (guards against
    # unrelated skills that happen to share a generic name like "helper").
    copy_similarity: float = 0.5

    # E3 bundled executables: file extensions treated as executable code.
    executable_extensions: tuple = field(
        default=(
            ".sh", ".bash", ".zsh", ".fish",
            ".py", ".js", ".mjs", ".cjs", ".ts",
            ".rb", ".pl", ".php", ".lua",
            ".ps1", ".psm1", ".bat", ".cmd",
            ".exe", ".bin", ".jar", ".appimage",
        )
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["executable_extensions"] = list(self.executable_extensions)
        return d
