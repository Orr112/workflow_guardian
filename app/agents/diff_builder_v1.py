from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


def _allowed_paths_from_json(evidence: dict[str, object]) -> list[str]:
    raw = evidence.get("allowed_paths.json")
    if raw is None:
        raise RuntimeError("DiffBuilderV1: missing allowed_paths.json evidence.")
    if not isinstance(raw, str):
        raw = str(raw)
    payload = json.loads(raw)
    allowed = payload.get("allowed_paths", [])
    if not isinstance(allowed, list):
        raise RuntimeError("DiffBuilderV1: allowed_paths.json missled allowed_paths list")
    return [str(p) for p in allowed]


def _is_allowed_path(path: str, allowed_paths: list[str]) -> bool:
    norm = path.strip().lstrip("./")
    for allowed in allowed_paths:
        allowed_norm = allowed.strip().lstrip("./")
        if allowed_norm.endswith("/"):
            if norm.startswith(allowed_norm):
                return True
        elif norm == allowed_norm:
            return True
    return False


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

def _proposed_paths_from_disk(ctx: RunContext, store: ArtifactStore) -> list[str]:
    """
    Discover proposed files by scanning the run artifacts directory on disk.

    Returns repo-relative paths like:
      scripts/refresh_data.py
      README.md
    """
    roots = _candidate_artifacts_roots(ctx, store)

    proposed_root: Path | None = None
    for root in roots:
        # root might already be artifacts/
        p1 = root / "proposed"
        if p1.exists() and p1.is_dir():
            proposed_root = p1
            break

        # root might be run_dir/, with artifacts inside it
        p2 = root / "artifacts" / "proposed"
        if p2.exists() and p2.is_dir():
            proposed_root = p2
            break

    if not proposed_root:
        return []

    out: list[str] = []
    for f in proposed_root.rglob("*"):
        if f.is_file():
            out.append(f.relative_to(proposed_root).as_posix())
    return sorted(set(out))


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

        allowed_paths = _allowed_paths_from_json(evidence)
        proposed_paths = _proposed_paths_from_evidence(evidence)

        # If YAML no longer enumerates proposed/* inputs, evidence may not include proposed/ keys.
        # In that case, discover proposed files directly from disk.
        if not proposed_paths:
            proposed_paths = _proposed_paths_from_disk(ctx, store)

        clean_proposed_paths: list[str] = []
        for p in proposed_paths:
            v = evidence.get(f"proposed/{p}")
            if isinstance(v, str) and v.startswith("[missing evidence:"):
                continue
            clean_proposed_paths.append(p)

        proposed_paths = clean_proposed_paths


        if not allowed_paths:
            raise RuntimeError("DiffBuilderV1: no allowed paths (missing files/<path>.txt evidence).")

        targets = [p for p in proposed_paths if _is_allowed_path(p, allowed_paths)]

        if not targets:
            rel = store.write_text("changes.patch", "(no changes)\n")
            return {"message": "No proposed file changes", "artifacts": [rel], "meta": {"targets": []}}

        repo_root = Path(ctx.repo_root).resolve()

        if not (repo_root / ".git").exists():
            raise RuntimeError(f"DiffBuilderV1: repo_root does not contain .git: {repo_root}")

        patch_parts: list[str] = []

        for path in targets:
            # OLD from repo working tree
            repo_file = repo_root / path
            old = repo_file.read_text(encoding="utf-8") if repo_file.exists() else ""

            # NEW from run artifacts
            # NEW from run artifacts (preferred), fallback to evidence if not materialized on disk
            try:
                proposed_file = _find_proposed_file(ctx, store, path)
                new = proposed_file.read_text(encoding="utf-8")
            except RuntimeError:
                new_key = f"proposed/{path}"
                new = bundle.evidence.get(new_key)

                if not isinstance(new, str) or not new.strip():
                    raise RuntimeError(
                        f"DiffBuilderV1: proposed content missing for {new_key} "
                        "(not on disk and not present in evidence)."
                    )

                if new.startswith("[missing evidence:"):
                    raise RuntimeError(f"DiffBuilderV1: proposed artifact missing: {new}")

                # Optional: materialize it so future stages/debugging can see it on disk
                store.write_text(f"proposed/{path}", new)

            if old and not old.endswith("\n"):
                old += "\n"
            if new and not new.endswith("\n"):
                new += "\n"

            if old == new:
                continue

            old_lines = old.splitlines()
            new_lines = new.splitlines()

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

            patch_parts.append(f"diff --git a/{path} b/{path}\n")
            patch_parts.extend(dl + "\n" for dl in diff_lines)

        patch_text = "".join(patch_parts)

        if not patch_text.strip():
            patch_text = "(no changes)\n"
        elif not patch_text.endswith("\n"):
            patch_text += "\n"

        rel = store.write_text("changes.patch", patch_text)

        return {
            "message": "Deterministic patch built from proposed full-file updates (disk-based)",
            "artifacts": [rel],
            "meta": {"targets": targets},
        }