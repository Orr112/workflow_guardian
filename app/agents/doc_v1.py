from __future__ import annotations

from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class DocV1(Agent):
    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        doc = (
            f"# Run Summary\n\n"
            f"**Project:** {bundle.project}\n"
            f"**Run:** {bundle.run_id}\n"
            f"**Task:** {bundle.task}\n\n"
            f"## Artifacts\n"
            + "\n".join([f"- {a}" for a in ctx.artifacts])
            + "\n"
        )

        rel = store.write_text("summary.md", doc)

        # Private notes (optional)
        ctx.private.setdefault("doc_v1", {})
        ctx.private["doc_v1"]["summary_path"] = rel

        return {"message": "Documentation summary written", "artifacts": [rel]}