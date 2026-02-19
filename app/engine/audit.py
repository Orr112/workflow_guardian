from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AuditLogEntry:
    timestamp: str
    entity_type: str
    from_state: str
    to_state: str
    risk_tier: str
    human_approved: bool
    allowed: bool
    reasons: tuple[str, ...]
    completeness_percent: Optional[int]


class AuditLogger:
    """
    Simple JSONL audit logger.
    Appends one JSON record per transition attempt
    """

    def __init__(self, path:Path):
        self._path = path

    def log(self, entry: AuditLogEntry) -> None:
        record = asdict(entry)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record))
            f.write("\n")

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()