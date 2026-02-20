from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from app.engine.completeness import CompletenessEngine, CompletenessResult
from app.models import GateRule


class GateError(ValueError):
    pass


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reasons: tuple[str, ...]
    completeness: Optional[CompletenessResult] = None


class GateEngine:
    """
    Evaluates gate specs for transitions.
    v1 supports:
      - completeness_min
      - require_human_approval: true/false/"medium_or_high"
    """

    def __init__(self):
        self._completeness = CompletenessEngine()

    def evaluate(
        self,
        *,
        checklist: Iterable[str],
        entity_data: Mapping[str, object],
        rules: list[GateRule],
        require_human_approval: bool | str,
        risk_tier: str,
        human_approved: bool,
    ) -> GateDecision:
        reasons: list[str] = []
        completeness_result: Optional[CompletenessResult] = None

        # Human approval policy
        if self._human_required(require_human_approval, risk_tier):
            if not human_approved:
                reasons.append("Human approval required but not provided.")

        # Rule evaluation (typed GateRule)
        for rule in rules:
            rule_type = rule.type.strip()

            if rule_type == "completeness_min":
                if rule.percent is None:
                    reasons.append("Rule completeness_min missing required 'percent'.")
                    continue

                completeness_result = self._completeness.compute(checklist, entity_data)
                if completeness_result.percent < int(rule.percent):
                    reasons.append(
                        f"Completeness {completeness_result.percent}% is below required {int(rule.percent)}%."
                    )
            else:
                reasons.append(f"Unsupported rule type: {rule_type}")

        return GateDecision(allowed=(len(reasons) == 0), reasons=tuple(reasons), completeness=completeness_result)

    @staticmethod
    def _human_required(require_human_approval: bool | str, risk_tier: str) -> bool:
        if isinstance(require_human_approval, bool):
            return require_human_approval

        if require_human_approval == "medium_or_high":
            return risk_tier in ("medium", "high")

        # Safe default
        return True