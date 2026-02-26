from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

@dataclass(frozen=True)
class ReviewLogEntry:
    timestamp: str
    provider: str
    model: str
    target_path: str
    content_sha256: str
    response_text: str


class ReviewArchive:
    def __init__(self, path: Path):
        self._path = path

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
    
    @staticmethod
    def sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    
    def append(self, entry: ReviewLogEntry) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)))
            f.write("\n")

