from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


def _git_ls_files(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

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

        repo_root = Path(ctx.repo_root).resolve()
        allowed_paths = _git_ls_files(repo_root)

        payload = {
            "repo_root": str(repo_root),
            "allowed_paths": allowed_paths,
        }

        rel_allowed = store.write_text("allowed_paths.json", json.dumps(payload, indent=2) + "\n")

        return {"message": "Repo index written", "artifacts": [rel]}