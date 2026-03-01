from __future__ import annotations

import re 
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext
from app.runtime.patch_tools import (
    sanitize_patch_output,
    validate_basic,
    PatchValidationError,
)


def _allowed_paths_from_evidence_keys(evidence: dict[str, object]) -> list[str]:
    allowed: list[str] = []
    for key in evidence.keys():
        if key.startswith("files/") and key.endswith(".txt"):
            allowed.append(key[len("files/") : -len(".txt")])
    return sorted(set(allowed))


PATCH_PROMPT = """\
You are a senior software engineer. Generate updated full-file contents that implement the TASK.

OUTPUT CONTRACT (must follow exactly):
- Output ONLY file blocks in the exact format below.
- NO commentary. NO markdown fences.
- You may ONLY modify files listed in ALLOWED_PATHS.
- Do NOT create or rename files.
- If you cannot implement, output exactly:
(no changes)

FILE BLOCK FORMAT (repeat for each modified file):
FILE: <path>
<full updated file contents>

TASK:
{task}

ALLOWED_PATHS:
{allowed_paths}

FILE_CONTENTS (source of truth; edit these exactly):
{file_context}

REPO TREE:
{repo_tree}
"""


FILE_BLOCK_RE = re.compile(r"^FILE:\s*(.+?)\s*$", re.MULTILINE)


def _parse_file_blocks(text: str) -> dict[str, str]:
    """
    Parse:
      FILE: path
      <content...>

    Returns dict[path] = content (full file contents)
    """
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
        content = t[start:end].lstrip("\n").rstrip() + "\n"
        blocks[path] = content

    return blocks


class CoderPatchLLMV1(Agent):
    def run(
        self,
        ctx: RunContext,
        bundle: ContextBundle,
        store: ArtifactStore,
    ) -> Dict[str, Any]:

        repo_tree = bundle.evidence.get("repo_tree.txt", "")
        allowed_paths = _allowed_paths_from_evidence_keys(bundle.evidence)

        if not allowed_paths:
            raise RuntimeError("No allowed paths found (missing file_context evidence).")

        # Build file context
        file_context_chunks = []
        for p in allowed_paths:
            k = f"files/{p}.txt"
            content = bundle.evidence.get(k, "")
            file_context_chunks.append(f"--- {p} ---\n{content}\n")
        file_context = "\n".join(file_context_chunks)
        allowed_paths_str = "\n".join(f"- {p}" for p in allowed_paths)

        prompt = PATCH_PROMPT.format(
            task=bundle.task,
            allowed_paths=allowed_paths_str,
            file_context=file_context,
            repo_tree=repo_tree[:120_000],
        )

        from app.llm.client import get_client, get_config

        client = get_client()
        cfg = get_config()

        def _extract_text(resp) -> str:
            parts = []
            for block in resp.content:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()

        def _call_llm(p: str, *, temperature: float) -> str:
            resp = client.messages.create(
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": p}],
            )
            return _extract_text(resp)

        # Attempt 1
        raw = _call_llm(prompt, temperature=0.2)

        try:
            blocks = _parse_file_blocks(raw)
        except ValueError:
            store.write_text("git/invalid_fullfile_raw.txt", raw + "\n")

            # Retry once, stricter
            retry_prompt = (
                "You did not follow the FILE BLOCK FORMAT.\n"
                "Return ONLY FILE blocks exactly like:\n"
                "FILE: <path>\\n<full file contents>\n"
                "No commentary. No markdown.\n\n"
                + prompt
            )
            raw2 = _call_llm(retry_prompt, temperature=0.0)
            store.write_text("git/invalid_fullfile_retry_raw.txt", raw2 + "\n")
            blocks = _parse_file_blocks(raw2)

        # Enforce allowed paths dynamically
        bad_paths = sorted([p for p in blocks.keys() if p not in allowed_paths])
        if bad_paths:
            rel = store.write_text(
                "git/fullfile_validation_error.txt",
                "Disallowed FILE blocks:\n" + "\n".join(bad_paths) + "\n",
            )
            raise RuntimeError(f"Coder produced disallowed file paths (see {rel}).")

        # Write proposed files as artifacts
        artifacts: list[str] = []
        for path, content in blocks.items():
            rel = store.write_text(f"proposed/{path}", content)
            artifacts.append(rel)

        ctx.private.setdefault("coder_patch_llm_v1", {})
        ctx.private["coder_patch_llm_v1"]["proposed_files"] = sorted(blocks.keys())
        ctx.private["coder_patch_llm_v1"]["patch_is_empty"] = (len(blocks) == 0)

        return {
            "message": "LLM proposed full-file updates",
            "artifacts": artifacts,
            "meta": {
                "allowed_paths": allowed_paths,
                "proposed_paths": sorted(blocks.keys()),
                "file_context_chars": len(file_context),
            },
        }