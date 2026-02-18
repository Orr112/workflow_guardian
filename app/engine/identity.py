from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


class IdentityError(ValueError):
    pass


@dataclass(frozen=True)
class IdentityResult:
    entity_type: str
    raw_id: str
    canonical_id: Optional[str]
    is_legacy: bool


class IdentityValidator:
    """
    Validates IDs against canonical + legacy patterns defined in the spec.
    For now, legacy IDs are detected (flagged) but not auto-converted.
    """

    def __init__(self, canonical_regex: str, legacy_regexes: list[str] | None = None):
        self._canonical = re.compile(canonical_regex)
        self._legacy = [re.compile(r) for r in (legacy_regexes or [])]

    def validate(self, entity_type: str, id_value: str) -> IdentityResult:
        if self._canonical.fullmatch(id_value):
            return IdentityResult(
                entity_type=entity_type,
                raw_id=id_value,
                canonical_id=id_value,
                is_legacy=False,
            )

        for legacy_re in self._legacy:
            if legacy_re.fullmatch(id_value):
                # Detected legacy format; in v2 we'll add optional normalization/conversion
                return IdentityResult(
                    entity_type=entity_type,
                    raw_id=id_value,
                    canonical_id=None,
                    is_legacy=True,
                )

        raise IdentityError(
            f"Invalid {entity_type} id '{id_value}'. Does not match canonical or legacy patterns."
        )
