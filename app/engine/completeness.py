from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


class CompletenessError(ValueError):
    pass


@dataclass(frozen=True)
class CompletenessResult:
    total_items: int
    satisfied_items: int
    percent: int  # 0..100 integer percent
    missing_items: tuple[str, ...]


class CompletenessEngine:
    """
    Computes completeness for an entity instance using a checklist defined in the spec.

    Entity instance is represented as a mapping of checklist item -> truthy/falsey value,
    e.g. {"has_title": True, "has_acceptance_criteria": False}.
    """

    def compute(
        self,
        checklist: Iterable[str],
        entity_data: Mapping[str, object],
    ) -> CompletenessResult:
        items = list(checklist)
        total = len(items)

        if total == 0:
            # If no checklist exists, treat as trivially complete.
            return CompletenessResult(
                total_items=0,
                satisfied_items=0,
                percent=100,
                missing_items=(),
            )

        satisfied = 0
        missing = []

        for item in items:
            # Missing keys are treated as not satisfied
            value = entity_data.get(item, False)
            if bool(value):
                satisfied += 1
            else:
                missing.append(item)

        # Integer percent, rounded down (predictable + testable)
        percent = (satisfied * 100) // total

        return CompletenessResult(
            total_items=total,
            satisfied_items=satisfied,
            percent=percent,
            missing_items=tuple(missing),
        )
