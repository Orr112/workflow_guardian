from __future__ import annotations

import json
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext

MODIFY_ONLY_RE = re.compile(
    r"Modify ONLY\s*:?\s*(.*?)(?:\n\s*\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _load_json_maybe(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return {}
        return json.loads(value)
    raise TypeError(f"Unsupported JSON evidence type: {type(value)}")


def _normalize_paths(paths: list[str]) -> list[str]:
    seen = set()
    out = []
    for p in paths:
        if not p:
            continue
        norm = str(p).strip().lstrip("./")
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _normalize_path_token(token: str) -> str:
    return token.strip().strip('"').strip("'").strip().lstrip("./")


def _extract_explicit_targets(task: str, allowed_paths: list[str]) -> list[str]:
    allowed_set = set(allowed_paths)
    targets: list[str] = []

    match = MODIFY_ONLY_RE.search(task)
    if match:
        block = match.group(1)
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        for line in lines:
            parts = re.split(r",|\band\b", line)
            for part in parts:
                p = _normalize_path_token(part)
                if p in allowed_set and p not in targets:
                    targets.append(p)

    if targets:
        return targets

    for path in allowed_paths:
        if path in task and path not in targets:
            targets.append(path)

    return targets


def _score_candidate_path(path: str, task: str) -> int:
    score = 0
    filename = Path(path).name
    stem = Path(path).stem
    low_task = task.lower()

    if filename.lower() in low_task:
        score += 10
    if stem.lower() in low_task:
        score += 5

    for part in Path(path).parts:
        low_part = part.lower()
        if low_part in low_task:
            score += 2

    return score


def _select_candidate_files(task: str, allowed_paths: list[str]) -> list[str]:
    explicit = _extract_explicit_targets(task, allowed_paths)
    if explicit:
        return explicit

    scored = []
    for path in allowed_paths:
        score = _score_candidate_path(path, task)
        if score > 0:
            scored.append((score, path))

    if scored:
        scored.sort(reverse=True)
        return [p for _, p in scored[:8]]

    preferred_prefixes = ("scripts/", "src/", "app/", "dashboard/", "docs/")
    fallback = [p for p in allowed_paths if p.startswith(preferred_prefixes)]
    if fallback:
        return fallback[:8]

    return allowed_paths[:8]


class PlannerV1(Agent):
    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        before_snapshot = bundle.evidence.get("git/before_snapshot.json", "")
        before_diff = bundle.evidence.get("git/before.diff", "")
        repo_tree = bundle.evidence.get("repo_tree.txt", "")
        allowed_paths_payload = bundle.evidence.get("allowed_paths.json", {})

        allowed_data = _load_json_maybe(allowed_paths_payload)
        allowed_paths = _normalize_paths(allowed_data.get("allowed_paths", []) or [])

        selected_paths = _select_candidate_files(bundle.task, allowed_paths)
        proposed_paths = list(selected_paths)

        validation_plan = [
            "Build patch only for selected paths",
            "Run targeted validation for changed files",
            "Run test stage and review resulting patch",
        ]

        if any(path.endswith(".py") for path in selected_paths):
            validation_plan.insert(1, "Validate generated Python syntax before patch application")

        plan: Dict[str, Any] = {
            "task": bundle.task,
            "summary": "Deterministic implementation plan based on task text and allowed paths",
            "input_used": {
                "git/before_snapshot.json_present": bool(str(before_snapshot).strip()),
                "git/before.diff_present": bool(str(before_diff).strip()),
                "repo_tree.txt_present": bool(str(repo_tree).strip()),
                "allowed_paths.json_present": bool(allowed_paths),
            },
            "selected_paths": selected_paths,
            "proposed_paths": proposed_paths,
            "assumptions": [
                "Repo root is available",
                "Only allowed paths may be modified",
                "Changes should be minimal and task-directed",
            ],
            "steps": [
                "Identify target files from the task and allowed paths",
                "Implement the minimal change in selected files",
                "Generate a patch from proposed file updates",
                "Run validation and review stages",
            ],
            "risks": [
                "Selected file may be incomplete for the requested change",
                "Task wording may underspecify validation needs",
                "No relevant tests may exist",
            ],
            "validation_plan": validation_plan,
            "constraints": {
                "must_follow_allowed_paths": True,
                "must_not_change_unlisted_files": True,
            },
        }

        rel = store.write_text("plan.json", json.dumps(plan, indent=2))

        ctx.private.setdefault("planner_v1", {})
        ctx.private["planner_v1"]["plan_summary"] = {
            "selected_paths_count": len(selected_paths),
            "selected_paths": selected_paths,
            "validation_steps": len(validation_plan),
        }

        return {
            "message": f"Plan created for {len(selected_paths)} file(s)",
            "artifacts": [rel],
            "meta": {
                "plan_keys": list(plan.keys()),
                "selected_paths": selected_paths,
                "proposed_paths": proposed_paths,
                "validation_plan_steps": len(validation_plan),
            },
        }
