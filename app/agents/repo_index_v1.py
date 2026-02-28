from __future__ import annotations

import subprocess
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class RepoIndexV1(Agent):
    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=str(ctx.repo_root),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr)

        rel = store.write_text("repo_tree.txt", proc.stdout)
        return {"message": "Repo index written", "artifacts": [rel]}