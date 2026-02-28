from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class FileContextV1(Agent):
    def __init__(self, paths: List[str]):
        self.paths = paths

    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        artifacts: list[str] = []
        missing: list[str] = []

        for p in self.paths:
            fp = ctx.repo_root / p
            if not fp.exists():
                missing.append(p)
                continue
            content = fp.read_text(encoding="utf-8")
            rel = store.write_text(f"files/{p}.txt", content)
            artifacts.append(rel)

        return {
            "message": "File context exported",
            "artifacts": artifacts,
            "meta": {"missing": missing, "count": len(artifacts)},
        }