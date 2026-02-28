from __future__ import annotations

from pathlib import Path

class ArtifactStore:
    def __init__(self, artifacts_dir: Path):
        self._dir = artifacts_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def write_text(self, rel_path: str, content: str) -> str:
        p = self._dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"{self._dir.name}/{rel_path}"
    