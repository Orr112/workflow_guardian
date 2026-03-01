from __future__ import annotations

from app.agents.apply_patch_v1 import ApplyPatchV1
from app.agents.coder_patch_v1 import CoderPatchV1
from app.agents.coder_patch_llm_v1 import CoderPatchLLMV1
from app.agents.diff_builder_v1 import DiffBuilderV1
from app.agents.file_context_v1 import FileContextV1
from app.agents.git_snapshot_v1 import GitSnapshotV1
from app.agents.manifest_v1 import ManifestV1
from app.agents.coder_v1 import CoderV1
from app.agents.doc_v1 import DocV1
from app.agents.planner_v1 import PlannerV1
from app.agents.reviewer_v1 import ReviewerV1
from app.agents.repo_index_v1 import RepoIndexV1
from app.agents.tester_v1 import TesterV1


def default_registry():
    return {
        "git_snapshot_before_v1": GitSnapshotV1(label="before"),
        "git_snapshot_after_v1": GitSnapshotV1(label="after"),
        "repo_index_v1": RepoIndexV1(),
        "planner_v1": PlannerV1(),
        "file_context_v1": FileContextV1(paths=["app/engine/gates.py", "tests/test_gates.py"]),
        "coder_patch_llm_v1": CoderPatchLLMV1(),
        "apply_patch_v1": ApplyPatchV1(),
        "diff_builder_v1": DiffBuilderV1(),
        "tester_v1": TesterV1(),
        "reviewer_v1": ReviewerV1(),
        "doc_v1": DocV1(),
        "manifest_v1": ManifestV1(),
    }