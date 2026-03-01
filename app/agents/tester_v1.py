from __future__ import annotations

import subprocess
from typing import Any, Dict

from app.agents.base import Agent
from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext


class TesterV1(Agent):
    def run(
        self,
        ctx: RunContext,
        bundle: ContextBundle,
        store: ArtifactStore,
    ) -> Dict[str, Any]:
        """
        Runs pytest in the repo root.
        Does not consume other agents' opinions — only raw repo state.
        """

        proc = subprocess.run(
            ["pytest", "-q"],
            cwd=str(ctx.repo_root),
            capture_output=True,
            text=True,
        )

        report = (
            f"exit_code={proc.returncode}\n\n"
            f"STDOUT:\n{proc.stdout}\n\n"
            f"STDERR:\n{proc.stderr}\n"
        )

        rel = store.write_text("test_report.txt", report)

        # Private memory (not shared automatically)
        ctx.private.setdefault("tester_v1", {})
        ctx.private["tester_v1"]["exit_code"] = proc.returncode

        # pytest exit codes:
        # 0 = all tests passed
        # 1 = tests failed
        # 5 = no tests collected
        if proc.returncode not in (0, 5):
            raise RuntimeError("pytest failed (see artifacts/test_report.txt)")

        status_msg = "pytest passed" if proc.returncode == 0 else "no tests collected"

        return {
            "message": status_msg,
            "artifacts": [rel],
            "meta": {"exit_code": proc.returncode},
        }