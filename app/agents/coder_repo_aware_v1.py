from __future__ import annotations

import ast
import json
import re
import time
import random
from pathlib import Path
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


REPO_AWARE_PROMPT = """\
You are a repo-aware senior software engineer working in a real code repository.

Your job is to implement the TASK by updating the current files below.

OUTPUT CONTRACT (must follow exactly):
- Output ONLY file blocks in the exact format below.
- NO commentary.
- NO markdown fences.
- You may ONLY modify files listed in ALLOWED_PATHS.
- Do NOT create, rename, or delete files.
- If no changes are needed, output exactly:
(no changes)

FILE BLOCK FORMAT (repeat for each modified file):
FILE: <path>
<full updated file contents>

TASK:
{task}

ALLOWED_PATHS:
{allowed_paths}

REPO TREE:
{repo_tree}

CURRENT FILE CONTENTS (source of truth):
{file_context}
"""


FILE_BLOCK_RE = re.compile(r"^FILE:\s*(.+?)\s*$", re.MULTILINE)
MODIFY_ONLY_RE = re.compile(
    r"Modify ONLY\s*:?\s*(.*?)(?:\n\s*\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _allowed_paths_from_json(evidence: dict[str, object]) -> list[str]:
    if "allowed_paths.json" not in evidence:
        raise RuntimeError(
            f"allowed_paths.json key not present in evidence. Keys: {sorted(evidence.keys())}"
        )

    raw = evidence["allowed_paths.json"]
    if raw is None:
        raise RuntimeError("allowed_paths.json evidence value is None.")

    if not isinstance(raw, str):
        raw = str(raw)

    payload = json.loads(raw)

    allowed = payload.get("allowed_paths")
    if allowed is None:
        # temporary backwards compatibility
        allowed = payload.get("allowed_path", [])

    if not isinstance(allowed, list):
        raise RuntimeError("allowed_paths.json missing allowed_paths list.")

    return sorted(set(str(p) for p in allowed))


def _read_repo_file(repo_root: Path, rel_path: str) -> str:
    path = (repo_root / rel_path).resolve()

    if not path.exists():
        return ""

    if path.is_dir():
        return f"[directory skipped: {rel_path}]"

    binary_ext = {
        ".xlsx", ".xls", ".xlsm",
        ".png", ".jpg", ".jpeg", ".gif",
        ".pdf", ".zip", ".tar", ".gz",
        ".pyc", ".pyo", ".so", ".dylib",
        ".db", ".sqlite", ".parquet",
    }

    if path.suffix.lower() in binary_ext:
        return f"[binary file skipped: {rel_path}]"

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = path.read_text(encoding="latin-1")
        except Exception:
            return f"[unreadable file skipped: {rel_path}]"

    if content and not content.endswith("\n"):
        content += "\n"
    return content



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
        norm = p.strip().lstrip("./")
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _is_generated_or_non_source_path(path: str) -> bool:
    """
    Exclude generated artifacts and data files from coder context selection.
    These files may exist in the repo, but the coder should not use them as
    editable/source context unless they are explicitly targeted.
    """
    generated_prefixes = (
        "runs/",
    )

    non_source_prefixes = (
        "data/",
    )

    source_suffixes = (
        ".py",
        ".md",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".sh",
    )

    if path.startswith(generated_prefixes):
        return True

    # Keep only source-like files out of data/ by default
    if path.startswith(non_source_prefixes):
        return True

    if not path.endswith(source_suffixes):
        return True

    return False



def _normalize_path_token(token: str) -> str:
    token = token.strip().strip('"').strip("'").strip()
    token = token.lstrip("./")
    return token


def _extract_explicit_targets(task: str, allowed_paths: list[str]) -> list[str]:
    """
    Extract paths from prompts like:

    Modify ONLY:
    scripts/simulate_bracket.py
    README.md

    Also supports simple single-line:
    Modify ONLY scripts/simulate_bracket.py and README.md.
    """
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
                if _is_allowed_path(p, allowed_paths) and p not in targets:
                    targets.append(p)

    # fallback: direct mentions anywhere in task
    if not targets:
        for token in re.findall(r"[A-Za-z0-9_./-]+", task):
            p = _normalize_path_token(token)
            if _is_allowed_path(p, allowed_paths) and p not in targets:
                targets.append(p)

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

    parts = [p.lower() for p in Path(path).parts]
    for part in parts:
        if part in low_task:
            score += 2

    return score


def _select_candidate_files(task: str, allowed_paths: list[str], repo_tree: str) -> list[str]:
    explicit = _extract_explicit_targets(task, allowed_paths)
    if explicit:
        return explicit

    # filter OUT runs/ and data/
    filtered_allowed = [p for p in allowed_paths if not _is_generated_or_non_source_path(p)]

    # pick files mentioned directly
    mentioned = []
    for path in filtered_allowed:
        if path in task and path not in mentioned:
            mentioned.append(path)
    if mentioned:
        return mentioned

    # score remaining
    scored = []
    for path in filtered_allowed:
        score = _score_candidate_path(path, task)
        if score > 0:
            scored.append((score, path))

    if scored:
        scored.sort(reverse=True)
        return [p for _, p in scored[:8]]

    return filtered_allowed[:8]



def _build_file_context(repo_root: Path, selected_paths: list[str]) -> str:
    chunks: list[str] = []
    for rel_path in selected_paths:
        content = _read_repo_file(repo_root, rel_path)
        chunks.append(f"--- {rel_path} ---\n{content}")
    return "\n".join(chunks)


def _parse_file_blocks(text: str) -> dict[str, str]:
    t = text.strip()
    if t == "(no changes)":
        return {}

    matches = list(FILE_BLOCK_RE.finditer(t))
    if not matches:
        raise ValueError("No FILE: blocks found")

    blocks: dict[str, str] = {}
    for i, m in enumerate(matches):
        path = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(t)
        content = t[start:end].lstrip("\n")
        if content and not content.endswith("\n"):
            content += "\n"
        blocks[path] = content

    return blocks

def _looks_truncated_python(content: str) -> bool:
    stripped = content.rstrip()

    if not stripped:
        return False

    bad_suffixes = ("(", "[", "{", ":", "\\", '"""', "'''")
    if stripped.endswith(bad_suffixes):
        return True

    tail = stripped.splitlines()[-1]
    if tail.count('"') % 2 != 0:
        return True
    if tail.count("'") % 2 != 0:
        return True

    return False


def _is_generated_or_non_source_path(path: str) -> bool:
    generated_prefixes = ("runs/",)
    non_source_prefixes = ("data/",)
    source_suffixes = (".py", ".md", ".yaml", ".yml", ".json", ".toml", ".sh")

    if path.startswith(generated_prefixes):
        return True

    if path.startswith(non_source_prefixes):
        return True

    if not path.endswith(source_suffixes):
        return True

    return False



def _validate_proposed_blocks(blocks: dict[str, str]) -> None:
    """
    Validate generated file contents before writing proposed artifacts.
    Currently enforces Python syntax correctness for*.py files.
    """
    for path, content in blocks.items():
        if path.endswith(".py"):
            if _looks_truncated_python(content):
                raise RuntimeError(f"Generated Python for {path} appears truncated.")

            try:
                ast.parse(content, filename=path)
            except SyntaxError as e:
                raise RuntimeError(f"Generated invalid python for {path}: {e}") from e


class CoderRepoAwareV1(Agent):
    def run(
        self,
        ctx: RunContext,
        bundle: ContextBundle,
        store: ArtifactStore,
    ) -> Dict[str, Any]:
        task = bundle.task

        repo_root = Path(ctx.repo_root).resolve()
        repo_tree = bundle.evidence.get("repo_tree.txt", "")
        allowed_paths_payload = bundle.evidence.get("allowed_paths.json", {})
        plan_payload = bundle.evidence.get("plan.json", {})
        
        plan = _load_json_maybe(plan_payload)
        allowed_data = _load_json_maybe(allowed_paths_payload)

        allowed_paths = allowed_data.get("allowed_paths", []) or []
        allowed_paths = _normalize_paths(allowed_paths)

        planned_selected_paths = _normalize_paths(plan.get("selected_paths", []) or [])
        planned_proposed_paths = _normalize_paths(plan.get("proposed_paths", []) or [])
        validation_plan = plan.get("validation_plan", []) or []


        planned_paths = []
        for path in [*planned_selected_paths, *planned_proposed_paths]:
            if path not in planned_paths:
                planned_paths.append(path)

        if planned_paths:
            candidate_paths = planned_paths
            selection_source = "plan"
        else:
            candidate_paths = _select_candidate_files(task, allowed_paths, repo_tree)
            candidate_paths = _normalize_paths(candidate_paths)
            selection_source = "auto"

        allowed_set = set(allowed_paths)
        filtered_paths = [
            p for p in candidate_paths
            if _is_allowed_path(p, allowed_paths) and not p.endswith("/")]
        
        rejected_paths = [
            p for p in candidate_paths
            if not _is_allowed_path(p, allowed_paths)]

        selected_paths = filtered_paths

        store.write_text( "debug/prompt_debug.txt",
                          f"slected_paths={selected_paths}\n"
                          f"allowed_paths_counts={len(allowed_paths)}\n"
        )

        if not selected_paths:
            raise RuntimeError("No candidate files selected from task and allowed paths.")

        if any(p.startswith("runs/") for p in selected_paths):
            raise RuntimeError(
                f"Invalid selected_paths for coder context: {selected_paths}. "
                "Generated files under runs/ must not be used as edit context."
            )


        if planned_paths and not filtered_paths:
            raise ValueError(
                "planner selected files, but none are inside allowed_paths.json. "
                f"planned={planned_paths} rejected={rejected_paths}"
            )

        if not allowed_paths:
            raise RuntimeError("No allowed paths found in allowed_paths.json.")

        if not filtered_paths:
            raise RuntimeError("No candidate files selected from task/plan and allowed paths.")

        file_context = _build_file_context(repo_root, filtered_paths)
        file_context_chars = len(file_context)

        allowed_paths_str = "\n".join(f"- {p}" for p in allowed_paths)


        prompt = REPO_AWARE_PROMPT.format(
            task=bundle.task,
            allowed_paths=allowed_paths_str,
            repo_tree=repo_tree[:120_000],
            file_context=file_context[:180_000],
        )

        from app.llm.client import get_client, get_config

        client = get_client()
        cfg = get_config()

        def _extract_text(resp: Any) -> str:
            parts: list[str] = []
            for block in getattr(resp, "content", []):
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()

        def _call_llm(p: str, *, temperature: float) -> str:
            retries = 5
            for attempt in range(retries):
                try:
                    resp = client.messages.create(
                        model=cfg.model,
                        max_tokens=cfg.max_tokens,
                        temperature=temperature,
                        messages=[{"role": "user", "content": p}],
                    )
                    return _extract_text(resp)
                except Exception as e:
                    msg = str(e).lower()
                    is_retryable = (
                        "overloaded" in msg
                        or "529" in msg
                        or "rate limit" in msg
                        or "timeout" in msg
                    )
                    if attempt == retries - 1 or not is_retryable:
                        raise
                    time.sleep((2 ** attempt) + random.random())

        raw = _call_llm(prompt, temperature=0.2)

        try:
            blocks = _parse_file_blocks(raw)
            _validate_proposed_blocks(blocks)
        except (ValueError, RuntimeError) as e:
            store.write_text("git/invalid_fullfile_raw.txt", raw + "\n")
            store.write_text("git/invalid_fullfile_error.txt", f"{type(e).__name__}: {e}\n")

            retry_prompt = (
                "Your previous output was invalid.\n"
                "Requirements:\n"
                "- Return ONLY FILE blocks exactly like:\n"
                "  FILE: <path>\\n<full file contents>\n"
                "- No commentary.\n"
                "- No markdown.\n"
                "- No placeholder comments.\n"
                "- No pass statements unless they already existed in the source file.\n"
                "- Ensure every Python file is complete and syntactically valid.\n"
                "- Do not truncate the file.\n\n"
                + prompt
            )
            raw2 = _call_llm(retry_prompt, temperature=0.0)
            store.write_text("git/invalid_fullfile_retry_raw.txt", raw2 + "\n")

            try:
                blocks = _parse_file_blocks(raw2)
                _validate_proposed_blocks(blocks)
            except (ValueError, RuntimeError) as e2:
                store.write_text("git/invalid_fullfile_retry_error.txt", f"{type(e2).__name__}: {e2}\n")
                raise

        bad_paths = sorted([p for p in blocks.keys() if not _is_allowed_path(p, allowed_paths)])
        if bad_paths:
            rel = store.write_text(
                "git/fullfile_validation_error.txt",
                "Disallowed FILE blocks:\n" + "\n".join(bad_paths) + "\n",
            )
            raise RuntimeError(f"Coder produced disallowed file paths (see {rel}).")

        artifacts: list[str] = []
        for path, content in blocks.items():
            rel = store.write_text(f"proposed/{path}", content)
            artifacts.append(rel)

        ctx.private.setdefault("coder_repo_aware_v1", {})
        ctx.private["coder_repo_aware_v1"]["selected_paths"] = filtered_paths
        ctx.private["coder_repo_aware_v1"]["proposed_files"] = sorted(blocks.keys())
        ctx.private["coder_repo_aware_v1"]["patch_is_empty"] = len(blocks) == 0



        return {
            "message": f"Prepared {len(filtered_paths)} proposed file(s)",
            "artifacts": artifacts,
            "meta": {
                "selection_source": selection_source,
                "selected_paths": filtered_paths,
                "planned_selected_paths": planned_selected_paths,
                "planned_proposed_paths": planned_proposed_paths,
                "rejected_paths": rejected_paths,
                "allowed_paths_count": len(allowed_paths),
                "validation_plan": validation_plan,
                "file_context_chars": file_context_chars,
            },
        }
