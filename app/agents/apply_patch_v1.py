from __future__ import annotations

import subprocess
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext
from app.runtime.git_tools import apply_patch, snapshot


class ApplyPatchV1(Agent):
    """
    Applies changes.patch to the working tree (Mode B).
    Safety:
      - requires clean working tree at start
      - reverts to pre-apply HEAD on failure
    """

    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        patch = bundle.evidence.get("changes.patch", "")
        if not patch.strip() or patch.strip().startswith("(no changes)"):
            raise RuntimeError("No patch to apply (changes.patch is empty).")

        # Require clean working tree at start
        pre = snapshot(ctx.repo_root)
        if pre.status.strip():
            raise RuntimeError(
                "Working tree is not clean. Commit/stash your changes before apply mode.\n"
                f"git status --porcelain:\n{pre.status}"
            )
        head_before = pre.head

        try:
            apply_patch(ctx.repo_root, patch)

            # record applied diff
            post_apply = snapshot(ctx.repo_root)
            rel_diff = store.write_text("git/applied.diff", post_apply.diff if post_apply.diff.strip() else "(no diff)\n")

            return {
                "message": "Patch applied to working tree",
                "artifacts": [rel_diff],
                "meta": {"head_before": head_before, "has_changes": bool(post_apply.status.strip())},
            }

        except Exception as e:
            # Revert hard to head_before (safest for Mode B)
            subprocess.run(["git", "reset", "--hard", head_before], cwd=str(ctx.repo_root), capture_output=True, text=True)
            raise RuntimeError(f"Apply failed and repo was reverted to {head_before}. Error: {e}") from e