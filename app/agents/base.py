from __future__ import annotations

from typing import Any, Dict

from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext

class Agent:
    def run(self, ctx: RunContext, bundle: ContextBundle, store: ArtifactStore) -> Dict[str, Any]:
        raise NotImplementedError