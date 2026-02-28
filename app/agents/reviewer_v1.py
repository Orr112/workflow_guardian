from __future__ import annotations

from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class ReviewerV1(Agent):
    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        patch = bundle.evidence.get("changes.patch", "")
        test_report = bundle.evidence.get("test_report.txt", "")

        # Build a review prompt from raw evidence only
        prompt = (
            "Review the following proposed patch and test results.\n\n"
            "## Patch\n"
            f"{patch}\n\n"
            "## Test Report\n"
            f"{test_report}\n"
        )

        try:
            from app.llm.reviewer import review_code  # noqa: WPS433 (local import intentional)
            review = review_code(prompt)
        except Exception as e:
            review = (
                "[REVIEWER FALLBACK]\n"
                "Could not run LLM reviewer.\n"
                f"{type(e).__name__}: {e}\n\n"
                "Inputs seen:\n"
                 f"- changes.patch present: {bool(patch.strip())}\n"
                f"- test_report.txt present: {bool(test_report.strip())}\n"
            )

        rel = store.write_text("review.md", review)

        # Store reviewer-only notes privately
        ctx.private.setdefault("reviewer_v1", {})
        ctx.private["reviewer_v1"]["review_length"] = len(review)

        return {"message": "Review generated for patch + test report", "artifacts": [rel]}