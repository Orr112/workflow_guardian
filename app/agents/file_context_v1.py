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

        for rel_path in self.paths:
            p = ctx.repo_root / rel_path
            if not p.exists():
                missing.append(rel_path)
                continue
            content = p.read_text(encoding="utf-8")
            # store under artifacts/files/... with a stable key
            out_rel = store.write_text(f"files/{rel_path}.txt", content)
            artifacts.append(out_rel)

        return {"message": "File context exported", "artifacts": artifacts, "meta": {"missing": missing}}