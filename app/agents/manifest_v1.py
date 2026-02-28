from __future__ import annotations

import json
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class ManifestV1(Agent):
    def run(
        self,
        ctx: RunContext,
        bundle: ContextBundle,
        store: ArtifactStore,
    ) -> Dict[str, Any]:

        git_private = ctx.private.get("git_snapshot_v1", {})
        coder_private = ctx.private.get("coder_patch_v1", {})

        manifest = {
            "run_id": ctx.run_id,
            "project": ctx.project,
            "task": ctx.task,
            "git_before": git_private.get("before"),
            "git_after": git_private.get("after"),
            "artifacts": list(ctx.artifacts),
            "proposed_patch": coder_private.get("proposed_patch_path"),
            "patch_is_empty": coder_private.get("patch_is_empty"),
        }

        rel = store.write_text("manifest.json", json.dumps(manifest, indent=2))

        # Store manifest privately for completeness (not required, but consistent)
        ctx.private.setdefault("manifest_v1", {})
        ctx.private["manifest_v1"]["manifest_path"] = rel

        return {
            "message": "Manifest written",
            "artifacts": [rel],
            "meta": {"artifact_count": len(ctx.artifacts)},
        }