from __future__ import annotations

from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class CoderPatchV1(Agent):
    """
    v1: produce a patch artifact (unified diff) WITHOT apply it.
    Later: can be backed by LLM to generate the diff.
    For now, it writes an explicit "(no change)" patch until we wire LLM diff generation
    """

    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        # v1 placeholder: real patch generation comes next (LLM-backed).
        patch = "(no changes)\n"

        rel = store.write_text("changes.patch", patch)

        # Private notes only (do not share automatically)
        ctx.private.setdefault("coder_patch_v1", {})
        ctx.private["coder_patch_v1"]["proposed_patch_path"] = rel
        ctx.private["coder_patch_v1"]["patch_is_empty"] = patch.strip() == "(no changes)"

        return {"message": "Patch artifact generated", "artifacts": [rel], "meta": {"applied": False}}