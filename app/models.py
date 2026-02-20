from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

class IdSpec(BaseModel):
    canonical_regex: str
    legacy_regexes: List[str] = []
    examples: List[str] = []

class GateRule(BaseModel):
    type: str
    percent: Optional[int] = None

class GateSpec(BaseModel):
    require_human_approval: bool | str
    rules: List[GateRule] = []

class TransitionSpec(BaseModel):
    from_state: str = Field(alias="from")
    to_state: str = Field(alias="to")
    gate: GateSpec

    model_config = ConfigDict(populate_by_name=True)

class EntitySpec(BaseModel):
    id: IdSpec
    checklist: List[str]
    states: List[str]
    transitions: List[TransitionSpec]

class GuardianSpec(BaseModel):
    risk_tiers: List[str]
    entities: Dict[str, EntitySpec]
    rules: Dict[str, Dict[str, Any]] = {}