from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


def _candidate_artifacts_roots(ctx: RunContext, store: ArtifactStore) -> list[Path]:
    candidates: list[Path] = []

    for obj, attrs in (
        (store, ("artifacts_dir", "artifacts_root", "base_dir", "root_dir", "dir", "path")),
        (ctx, ("artifacts_dir", "artifacts_root", "run_artifacts_dir", "run_dir", "runs_dir")),
    ):
        for attr in attrs:
            v = getattr(obj, attr, None)
            if not v:
                continue
            p = Path(v)
            candidates.append(p)
            candidates.append(p / "artifacts")

    seen: set[str] = set()
    uniq: list[Path] = []
    for p in candidates:
        key = str(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


class CleanupSuccessV1(Agent):
    def run(
        self,
        ctx: RunContext,
        bundle: ContextBundle,
        store: ArtifactStore,
    ) -> Dict[str, Any]:
        proposed_dir: Path | None = None

        for root in _candidate_artifacts_roots(ctx, store):
            cand = root / "proposed"
            if cand.exists() and cand.is_dir():
                proposed_dir = cand
                break

        if not proposed_dir:
            rel = store.write_text("cleanup/noop.txt", "No proposed directory found.\n")
            return {
                "message": "No proposed directory found",
                "artifacts": [rel],
                "meta": {"deleted": False},
            }

        shutil.rmtree(proposed_dir)

        rel = store.write_text(
            "cleanup/proposed_deleted.txt",
            f"Deleted proposed artifacts directory: {proposed_dir}\n",
        )

        return {
            "message": "Deleted proposed artifacts after successful run",
            "artifacts": [rel],
            "meta": {"deleted": True, "path": str(proposed_dir)},
        }