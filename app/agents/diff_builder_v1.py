from __future__ import annotations

import difflib
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


def _allowed_paths_from_evidence(evidence: dict[str, object]) -> list[str]:
    # keys like: files/app/engine/gates.py.txt  -> app/engine/gates.py
    out: list[str] = []
    for k in evidence.keys():
        if k.startswith("files/") and k.endswith(".txt"):
            out.append(k[len("files/") : -len(".txt")])
    return sorted(set(out))


def _proposed_paths_from_evidence(evidence: dict[str, object]) -> list[str]:
    # keys like: proposed/app/engine/gates.py -> app/engine/gates.py
    out: list[str] = []
    for k in evidence.keys():
        if k.startswith("proposed/"):
            out.append(k[len("proposed/") :])
    return sorted(set(out))


class DiffBuilderV1(Agent):
    """
    Builds a deterministic git-style patch from:
      - originals: files/<path>.txt
      - proposed:  proposed/<path>
    Produces: changes.patch
    """

    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        evidence = bundle.evidence

        allowed_paths = _allowed_paths_from_evidence(evidence)
        proposed_paths = _proposed_paths_from_evidence(evidence)

        if not allowed_paths:
            raise RuntimeError("DiffBuilderV1: no allowed paths (missing files/<path>.txt evidence).")

        # Only build diffs for proposed files that are allowed
        targets = [p for p in proposed_paths if p in allowed_paths]

        if not targets:
            # No proposed files => no changes
            rel = store.write_text("changes.patch", "(no changes)\n")
            return {"message": "No proposed file changes", "artifacts": [rel], "meta": {"targets": []}}

        patch_parts: list[str] = []

        for path in targets:
            old_key = f"files/{path}.txt"
            new_key = f"proposed/{path}"

            old = evidence.get(old_key, "")
            new = evidence.get(new_key, "")

            if not isinstance(old, str):
                old = str(old)
            if not isinstance(new, str):
                new = str(new)

            # Normalize to end with newline (reduces diff weirdness)
            if old and not old.endswith("\n"):
                old += "\n"
            if new and not new.endswith("\n"):
                new += "\n"

            if old == new:
                continue

            old_lines = old.splitlines(keepends=True)
            new_lines = new.splitlines(keepends=True)

            diff_lines = list(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                    lineterm="",
                    n=3,
                )
            )

            # difflib emits:
            # --- a/path
            # +++ b/path
            # @@ ...
            # We'll prepend a git-style header that git apply likes.
            patch_parts.append(f"diff --git a/{path} b/{path}\n")
            patch_parts.extend([line + "\n" for line in diff_lines])
            if not patch_parts[-1].endswith("\n"):
                patch_parts[-1] += "\n"

        patch_text = "".join(patch_parts).strip() + "\n"
        if not patch_text.strip():
            patch_text = "(no changes)\n"

        rel = store.write_text("changes.patch", patch_text)

        return {
            "message": "Deterministic patch built from proposed full-file updates",
            "artifacts": [rel],
            "meta": {"targets": targets},
        }