from __future__ import annotations

from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext
from app.runtime.patch_tools import sanitize_patch_output, validate_basic, PatchValidationError


PATCH_PROMPT = """\
You are a senior software engineer. Generate a unified diff patch (git-style) that implements the TASK.

Rules:
- Output ONLY the patch text. No markdown. No commentary.
- Patch must be minimal and focused.
- Use existing project style.
- If you need to add tests, use pytest.
- Do NOT change unrelated files.
- If you cannot confidently implement, output an empty patch (no changes) — but try hard first.

TASK:
{task}

REPO TREE (tracked files):
{repo_tree}

OPTIONAL CONTEXT (raw evidence):
- before diff:
{before_diff}

- plan.json:
{plan_json}
"""


class CoderPatchLLMV1(Agent):
    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        repo_tree = bundle.evidence.get("repo_tree.txt", "")
        before_diff = bundle.evidence.get("git/before.diff", "")
        plan_json = bundle.evidence.get("plan.json", "")

        prompt = PATCH_PROMPT.format(
            task=bundle.task,
            repo_tree=repo_tree[:120_000],
            before_diff=before_diff[:50_000],
            plan_json=plan_json[:50_000],
        )

        # Use Claude (single-call, isolated)
        from app.llm.client import get_client, get_config  # local import intentional

        client = get_client()
        cfg = get_config()

        resp = client.messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = (resp.content[0].text or "").strip()

        try:
            patch = sanitize_patch_output(raw)
            validate_basic(patch)
        except PatchValidationError:
            # Save raw output for debugging, but mark invalid so apply stage refuses
            patch = "(invalid patch)\n" + raw + ("\n" if not raw.endswith("\n") else "") 

        if "```" in patch:
            raise PatchValidationError("Fence survived sanitization")
              
        if not patch:
            patch = "(no changes)\n"

        rel = store.write_text("changes.patch", patch + ("\n" if not patch.endswith("\n") else ""))

        ctx.private.setdefault("coder_patch_llm_v1", {})
        ctx.private["coder_patch_llm_v1"]["patch_is_empty"] = patch.startswith("(no changes)")

        return {"message": "LLM patch generated", "artifacts": [rel]}