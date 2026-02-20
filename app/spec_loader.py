from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from app.models import GuardianSpec

def load_spec(spec_path: str | Path) -> GuardianSpec:
    path = Path(spec_path)
    raw: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GuardianSpec.model_validate(raw)
