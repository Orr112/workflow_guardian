from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional


class StoreError(ValueError):
    pass


@dataclass
class EntityRecord:
    entity_type: str
    entity_id: str
    risk_tier: str
    state: str
    data: Dict[str, Any]


class FileEntityStore:
    """
    Simple file-backed store.
    Writes entities into a single JSON file: entities.json
    """

    def __init__(self, path: Path):
        self._path = path

    def _read_all(self) -> Dict[str, Dict[str, Any]]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write_all(self, payload: Dict[str, Dict[str, Any]]) -> None:
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, entity_type: str, entity_id: str) -> Optional[EntityRecord]:
        payload = self._read_all()
        key = f"{entity_type}:{entity_id}"
        if key not in payload:
            return None
        rec = payload[key]
        return EntityRecord(**rec)

    def upsert(self, record: EntityRecord) -> None:
        payload = self._read_all()
        key = f"{record.entity_type}:{record.entity_id}"
        payload[key] = asdict(record)
        self._write_all(payload)

    def require(self, entity_type: str, entity_id: str) -> EntityRecord:
        rec = self.get(entity_type, entity_id)
        if rec is None:
            raise StoreError(f"Entity not found: {entity_type} {entity_id}")
        return rec
