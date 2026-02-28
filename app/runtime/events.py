from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class AgentEvent:
    run_id: str
    project: str
    stage: str
    agent: str
    timestamp: str

    status: str #"Ok" | "error"
    message: str

    artifacts: List[str]
    meta: Optional[Dict[str, Any]] = None