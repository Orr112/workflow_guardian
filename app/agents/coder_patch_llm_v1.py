from __future__ import annotations

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
You are a senior software engineer. Generate a full updated file patch (git-style) that implements the TASK.

OUTPUT CONTRACT (must follow exactly):
- Output the FULL updated contents of each modified file.
- The FIRST line MUST start with: updated file --git
- No commentary. No markdown fences.
- You may ONLY modify files listed in ALLOWED_PATHS.
- Do NOT create or rename files.
- If you cannot produce a valid patch, output exactly:
(no changes)

TASK:
{task}

ALLOWED_PATHS:
{allowed_paths}

FILE_CONTENTS (source of truth):
{file_context}

REPO TREE:
{repo_tree}
"""


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

        # First attempt
        resp = client.messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = _extract_text(resp)

        try:
            patch = sanitize_patch_output(raw)
            validate_basic(patch)

        except PatchValidationError:
            store.write_text("git/invalid_patch_raw.txt", raw + "\n")

            # Retry once with stricter instruction
            retry_prompt = (
                "You did not comply with the output contract.\n"
                "Return ONLY a unified diff patch starting with 'diff --git'.\n"
                "No commentary. No markdown fences.\n\n"
                + prompt
            )

            resp2 = client.messages.create(
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                temperature=0.0,
                messages=[{"role": "user", "content": retry_prompt}],
            )

            raw2 = _extract_text(resp2)
            store.write_text("git/invalid_patch_retry_raw.txt", raw2 + "\n")

            patch = sanitize_patch_output(raw2)
            validate_basic(patch)

        if "```" in patch:
            rel = store.write_text("git/sanitized_patch_debug.txt", patch)
            raise PatchValidationError(
                f"Fence survived sanitization (see {rel})"
            )

        if not patch.strip():
            patch = "(no changes)\n"

        rel = store.write_text(
            "changes.patch",
            patch if patch.endswith("\n") else patch + "\n",
        )

        ctx.private.setdefault("coder_patch_llm_v1", {})
        ctx.private["coder_patch_llm_v1"]["patch_is_empty"] = patch.startswith(
            "(no changes)"
        )

        return {
            "message": "LLM patch generated",
            "artifacts": [rel],
            "meta": {
                "allowed_paths": allowed_paths,
                "file_context_chars": len(file_context),
            },
        }