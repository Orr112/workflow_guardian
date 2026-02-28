from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class ContextBundle:
    """
    What an agent is allowed to see for a stage.
    Contains raw evidence (facts), not other agents' internal reasoning
    """
    task: str
    repo_root: Path
    stage: str
    run_id: str
    project: str
    evidence: Dict[str, Any]


@dataclass
class RunContext:
    run_id: str
    project: str
    task: str
    repo_root: Path

    run_dir: Path
    artifacts_dir: Path

    # Shared facts only (safe to share)
    # evidence_index maps logical artifact keys (e.g. "changes.patch")
    evidence_index: Dict[str, str] = field(default_factory=dict)

    # Private outputs per agent (NOT shared unless explicitly allowed)
    private: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # List of artifacts paths relative to run_dir
    # to artifact-relative paths (e.g. "artifacts/changes.patch")
    artifacts: List[str] = field(default_factory=list)
