from __future__ import annotations

import json
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext
from app.runtime.git_tools import snapshot


class GitSnapshotV1(Agent):
    def __init__(self, label: str):
        self.label = label  # "before" or "after"

    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        snap = snapshot(ctx.repo_root)

        payload = {
            "label": self.label,
            "head": snap.head,
            "status_porcelain": snap.status,
            "has_changes": bool(snap.status.strip() or snap.diff.strip()),
        }

        rel_meta = store.write_text(f"git/{self.label}_snapshot.json", json.dumps(payload, indent=2))
        rel_diff = store.write_text(f"git/{self.label}.diff", snap.diff if snap.diff.strip() else "(no diff)\n")

        # Store private snapshot info (not shared automatically)
        ctx.private.setdefault("git_snapshot_v1", {})
        ctx.private["git_snapshot_v1"][self.label] = payload

        return {
            "message": f"Captured git snapshot ({self.label})",
            "artifacts": [rel_meta, rel_diff],
            "meta": {
                "head": snap.head,
                "has_changes": payload["has_changes"],
            },
        }