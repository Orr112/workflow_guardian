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
            # split on commas / "and" for inline lists
            parts = re.split(r",|\band\b", line)
            for part in parts:
                p = _normalize_path_token(part)
                if p in allowed_set and p not in targets:
                    targets.append(p)

    if targets:
        return targets

    # fallback: direct mentions anywhere in task
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

    parts = [p.lower() for p in Path(path).parts]
    for part in parts:
        if part in low_task:
            score += 2

    return score


def _select_candidate_files(task: str, allowed_paths: list[str], repo_tree: str) -> list[str]:
    """
    Heuristic selection:
    1. Honor explicit "Modify ONLY" paths if present
    2. Otherwise choose paths mentioned in the task
    3. Otherwise score likely relevant files and take a small set
    """
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

    # final fallback: a small set from top-level files likely to matter
    preferred_prefixes = ("scripts/", "src/", "app/", "dashboard/", "docs/")
    fallback = [p for p in allowed_paths if p.startswith(preferred_prefixes)]
    if fallback:
        return fallback[:8]

    return allowed_paths[:8]


def _read_repo_file(repo_root: Path, rel_path: str) -> str:
    path = (repo_root / rel_path).resolve()
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    if content and not content.endswith("\n"):
        content += "\n"
    return content


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
        repo_root = Path(ctx.repo_root).resolve()
        repo_tree = bundle.evidence.get("repo_tree.txt", "")
        allowed_paths = _allowed_paths_from_json(bundle.evidence)

        if not allowed_paths:
            raise RuntimeError("No allowed paths found in allowed_paths.json.")

        selected_paths = _select_candidate_files(bundle.task, allowed_paths, repo_tree)

        if not selected_paths:
            raise RuntimeError("No candidate files selected from task and allowed paths.")

        file_context = _build_file_context(repo_root, selected_paths)
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
                    #Debug
                    store.write_text(
                        "debug/llm_response_meta.txt",
                        f"stop_reason={getattr(resp, 'stop_reason', None)}\n"
                        f"model={getattr(resp, 'model', None)}\n"
                        f"usage={getattr(resp, 'usage', None)}\n"
                    )

                    raw_text = _extract_text(resp)
                    store.write_text(
                        "debug/llm_response_tail.txt",
                        f"chars={len(raw_text)}\n\nLAST_1000_CHARS:\n{raw_text[-1000:]}\n"
                    )
                    return raw_text
                    # end of debug

                    #return _extract_text(resp)
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
        # Debug
        store.write_text(
                "debug/prompt_debug.txt",
                f"selected_paths={selected_paths}\n"
                f"prompt_chars={len(prompt)}\n"
                f"file_context_chars={len(file_context)}\n"
                )
        # end Debug
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

        allowed_set = set(allowed_paths)
        bad_paths = sorted([p for p in blocks.keys() if p not in allowed_set])
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
        ctx.private["coder_repo_aware_v1"]["selected_paths"] = selected_paths
        ctx.private["coder_repo_aware_v1"]["proposed_files"] = sorted(blocks.keys())
        ctx.private["coder_repo_aware_v1"]["patch_is_empty"] = len(blocks) == 0

        meta = {
            "allowed_paths_count": len(allowed_paths),
            "selected_paths": selected_paths,
            "proposed_paths": sorted(blocks.keys()),
            "file_context_chars": len(file_context),
        }

        return {
            "message": "Repo-aware LLM proposed full-file updates",
            "artifacts": artifacts,
            "meta": meta,
        }