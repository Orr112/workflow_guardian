from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

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
    from_state: str
    to_state: str
    gate: GateSpec

class EntitySpec(BaseModel):
    id: IdSpec
    checklist: List[str]
    states: List[str]
    transitions: List[Dict[str, Any]]

class GuardianSpec(BaseModel):
    risk_tiers: List[str]
    entities: Dict[str, EntitySpec]
    rules: Dict[str, Dict[str, Any]]