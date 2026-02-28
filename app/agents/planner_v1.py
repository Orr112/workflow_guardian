from __future__ import annotations

import json
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class PlannerV1(Agent):
    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        before_snapshot = bundle.evidence.get("git/before_snapshot.json", "")
        before_diff = bundle.evidence.get("git/before.diff", "")

        plan: Dict[str, Any] = {
            "task": bundle.task,
            "input_used": {
                "git/before_snapshot.json_present": bool(before_snapshot.strip()),
                "git/before.diff_present": bool(before_diff.strip()),
            },
            "assumptions": ["Repo root is available", "We can run pytest locally"],
            "steps": [
                "Identify files to change (based on task + repo evidence)",
                "Implement minimal change",
                "Add/adjust tests",
                "Run pytest + ruff",
                "Write brief docs/changelog note",
            ],
            "risks": ["Breaking API", "Test flakiness", "Spec mismatch"],
        }

        rel = store.write_text("plan.json", json.dumps(plan, indent=2))
        
         # Store planner-only notes privately (NOT shared unless explicitly surfaced as evidence)
        ctx.private.setdefault("planner_v1", {})
        ctx.private["planner_v1"]["plan_summary"] = f"{len(plan['steps'])} steps; {len(plan['risks'])} risks"

        return {"message": "Plan created", "artifacts": [rel], "meta": {"plan_keys": list(plan.keys())}}