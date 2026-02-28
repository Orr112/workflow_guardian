from __future__ import annotations

from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class CoderV1(Agent):
    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        proposal = (
            f"CODE PROPOSAL for task:\n{bundle.task}\n\n"
            "Suggested approach:\n"
            "- Locate relevant modules\n"
            "- Make minimal change\n"
            "- Update/add tests\n"
            "- Run pytest + ruff\n"
        )

        rel = store.write_text("code_proposal.txt", proposal)

        # Private notes only
        ctx.private.setdefault("coder_v1", {})
        ctx.private["coder_v1"]["proposal_path"] = rel

        return {"message": "Code proposal written", "artifacts": [rel]}