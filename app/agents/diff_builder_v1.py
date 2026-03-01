from __future__ import annotations

import difflib
from pathlib import Path
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


def _as_path(value: object) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value)
    return None


def _candidate_artifacts_roots(ctx: RunContext, store: ArtifactStore) -> list[Path]:
    """
    Try hard to locate the run's artifacts directory on disk.

    We don't assume exact attribute names; we probe common ones and also
    try ctx.run_dir / 'artifacts' and ctx.runs_dir/run_id patterns.
    """
    candidates: list[Path] = []

    # Common ArtifactStore attributes
    for attr in (
        "artifacts_dir",
        "artifacts_root",
        "base_dir",
        "root_dir",
        "dir",
        "path",
    ):
        p = _as_path(getattr(store, attr, None))
        if p:
            candidates.append(p)

    # Common RunContext attributes
    for attr in (
        "artifacts_dir",
        "artifacts_root",
        "run_artifacts_dir",
        "run_dir",
        "runs_dir",
    ):
        p = _as_path(getattr(ctx, attr, None))
        if p:
            candidates.append(p)

    # Heuristic: if we have a run_dir, artifacts are often in run_dir/artifacts
    run_dir = _as_path(getattr(ctx, "run_dir", None))
    if run_dir:
        candidates.append(run_dir / "artifacts")

    # De-dup + normalize
    uniq: list[Path] = []
    seen: set[str] = set()
    for c in candidates:
        try:
            cc = c.resolve()
        except Exception:
            cc = c
        key = str(cc)
        if key not in seen:
            seen.add(key)
            uniq.append(cc)

    return uniq


def _find_proposed_file(ctx: RunContext, store: ArtifactStore, rel_path: str) -> Path:
    """
    Find proposed/<rel_path> within the run artifacts directory.

    We probe likely roots and accept either:
      <root>/proposed/<rel_path>
    or if <root> is already .../artifacts:
      <root>/proposed/<rel_path>

    If nothing exists, raise with a helpful diagnostic.
    """
    rel_path = rel_path.lstrip("/")

    roots = _candidate_artifacts_roots(ctx, store)

    tried: list[Path] = []
    for root in roots:
        # root might already be the artifacts dir
        p1 = root / "proposed" / rel_path
        tried.append(p1)
        if p1.exists() and p1.is_file():
            return p1

        # root might be run_dir, with artifacts inside it
        p2 = root / "artifacts" / "proposed" / rel_path
        tried.append(p2)
        if p2.exists() and p2.is_file():
            return p2

    diagnostics = "\n".join(f"- {p}" for p in tried[:50])
    raise RuntimeError(
        "DiffBuilderV1: proposed file not found on disk.\n"
        f"Expected proposed/{rel_path}\n"
        "Tried:\n"
        f"{diagnostics}\n"
        "If the proposed files exist, your ArtifactStore/RunContext likely uses a different base directory; "
        "add its attribute name to _candidate_artifacts_roots()."
    )


class DiffBuilderV1(Agent):
    """
    Builds a deterministic git-style patch.

    IMPORTANT: Reads file contents from disk (not from evidence), to avoid
    stage-to-stage evidence propagation mismatches.

    - old: repo working tree at ctx.repo_root/<path>
    - new: run artifacts proposed/<path>
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
            rel = store.write_text("changes.patch", "(no changes)\n")
            return {"message": "No proposed file changes", "artifacts": [rel], "meta": {"targets": []}}

        repo_root = Path(ctx.repo_root).resolve()

        if not (repo_root / ".git").exists():
            raise RuntimeError(f"DiffBuilderV1: repo_root does not contain .git: {repo_root}")
        patch_parts: list[str] = []

        
        for path in targets:
            # OLD: read directly from repo working tree (source of truth for git apply)
            repo_file = repo_root / path
            old = repo_file.read_text(encoding="utf-8") if repo_file.exists() else ""

            print("DEBUG repo_root:", repo_root.resolve())
            print("DEBUG repo_file exists:", repo_file.exists())
            
            # NEW: read proposed content from evidence (still fine) BUT fail fast if missing
            new_key = f"proposed/{path}"
            new = evidence.get(new_key, "")

            if isinstance(new, str) and new.startswith("[missing evidence:"):
                raise RuntimeError(f"DiffBuilderV1: missing proposed content for {new_key}: {new}")

            # --- NEW from run artifacts filesystem (source of truth) ---
            proposed_file = _find_proposed_file(ctx, store, path)
            new = proposed_file.read_text(encoding="utf-8")

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

            # Prepend a git-style header that git apply likes.
            patch_parts.append(f"diff --git a/{path} b/{path}\n")
            patch_parts.extend([line + "\n" for line in diff_lines])

            # Ensure file separation newline
            if patch_parts and not patch_parts[-1].endswith("\n"):
                patch_parts[-1] += "\n"

        patch_text = "".join(patch_parts).strip() + "\n"
        if not patch_text.strip():
            patch_text = "(no changes)\n"

        rel = store.write_text("changes.patch", patch_text)

        return {
            "message": "Deterministic patch built from proposed full-file updates (disk-based)",
            "artifacts": [rel],
            "meta": {"targets": targets},
        }