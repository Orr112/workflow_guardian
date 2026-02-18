from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import ValidationError

from app.models import GuardianSpec, TransitionSpec

def load_spec(spec_path: str | Path) -> GuardianSpec:
    path = Path(spec_path)
    raw: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))

    spec = GuardianSpec.model_validate(raw)

    # Normalize transitions into TransitionSpec objects
    for entity_name, entity in spec.entities.items():
        normalized = []
        for t in entity.transitions:
           # YAML uses keys "from"/"to " - map them to python-friendly names
           normalized.append(
               TransitionSpec(
                   from_state=t["from"],
                   to_state=t["to"],
                   gate=t["gate"],
               ).model_dump()
           ) 
        spec.entities[entity_name].transitions = normalized

    return spec
