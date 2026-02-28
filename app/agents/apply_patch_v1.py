from __future__ import annotations

import subprocess
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext
from app.runtime.git_tools import snapshot


def _run_git_apply(
    *,
    repo_root: str,
    patch_text: str,
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    """
    Run git apply with patch piped via stdin.
    Returns CompletedProcess; caller decides how to handle errors.
    """
    return subprocess.run(
        ["git", "apply", *args, "-"],
        cwd=repo_root,
        input=patch_text,
        text=True,
        capture_output=True,
    )


class ApplyPatchV1(Agent):
    """
    Applies changes.patch to the working tree (Mode B).

    Safety:
      - requires clean working tree at start
      - validates patch applies cleanly before applying
      - uses --3way + --recount to reduce failures from line drift
      - reverts to pre-apply HEAD on failure
    """

    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        patch = bundle.evidence.get("changes.patch", "")
        if not patch.strip() or patch.strip().startswith("(no changes)"):
            raise RuntimeError("No patch to apply (changes.patch is empty).")

        if patch.lstrip().startswith("(invalid patch)"):
            raise RuntimeError("Patch is invalid (changes.patch marked invalid). Not applying.")

        # Require clean working tree at start
        pre = snapshot(ctx.repo_root)
        if pre.status.strip():
            raise RuntimeError(
                "Working tree is not clean. Commit/stash your changes before apply mode.\n"
                f"git status --porcelain:\n{pre.status}"
            )
        head_before = pre.head

        repo_root_str = str(ctx.repo_root)

        try:
            # 1) Preflight: does this patch apply?
            check_proc = _run_git_apply(
                repo_root=repo_root_str,
                patch_text=patch,
                args=["--check", "--recount"],
            )
            if check_proc.returncode != 0:
                err = (
                    "git apply --check failed\n\n"
                    f"STDOUT:\n{check_proc.stdout}\n\n"
                    f"STDERR:\n{check_proc.stderr}\n"
                )
                rel_err = store.write_text("git/apply_check_error.txt", err)
                raise RuntimeError(f"Patch failed preflight check (see {rel_err}).")

            # 2) Apply for real
            apply_proc = _run_git_apply(
                repo_root=repo_root_str,
                patch_text=patch,
                args=[ "--recount"],
            )
            if apply_proc.returncode != 0:
                err = (
                    "git apply failed\n\n"
                    f"STDOUT:\n{apply_proc.stdout}\n\n"
                    f"STDERR:\n{apply_proc.stderr}\n"
                )
                rel_err = store.write_text("git/apply_error.txt", err)
                raise RuntimeError(f"git apply failed (see {rel_err}).")

            # 3) Record applied diff + status
            post_apply = snapshot(ctx.repo_root)
            rel_diff = store.write_text(
                "git/applied.diff",
                post_apply.diff if post_apply.diff.strip() else "(no diff)\n",
            )
            rel_status = store.write_text(
                "git/applied_status.txt",
                post_apply.status if post_apply.status.strip() else "(clean)\n",
            )

            return {
                "message": "Patch applied to working tree",
                "artifacts": [rel_diff, rel_status],
                "meta": {
                    "head_before": head_before,
                    "has_changes": bool(post_apply.status.strip()),
                },
            }

        except Exception as e:
            # Revert hard to head_before (safest for Mode B)
            subprocess.run(
                ["git", "reset", "--hard", head_before],
                cwd=repo_root_str,
                capture_output=True,
                text=True,
            )
            raise RuntimeError(
                f"Apply failed and repo was reverted to {head_before}. Error: {e}"
            ) from e