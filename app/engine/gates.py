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
    - require_human_approval: true/false/"medium_or_hight" (Option B)
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
        reasons = []
        completeness_result: Optional[CompletenessResult] = None

        if self._human_required(require_human_approval, risk_tier):
            if not human_approved:
                reasons.append("Human approval required but not provided")

        for rule in rules:
            # Support both Pydantic models and raw dicts
            rule_type = getattr(rule, "type", None)
            if rule_type is None and isinstance(rule, dict):
                rule_type = rule.get("type")

            rule_type = (str(rule_type) if rule_type is not None else "").strip()

            if rule_type == "completeness_min":
                percent = getattr(rule, "percent", None)
                if percent is None and isinstance(rule, dict):
                    percent = rule.get("percent")

                if percent is None:
                    reasons.append("Rule completeness_min missing required 'percent'.")
                    continue

                completeness_result = self._completeness.compute(checklist, entity_data)
                if completeness_result.percent < int(percent):
                    reasons.append(
                        f"Completeness {completeness_result.percent}% is below required {int(percent)}%."
                    )
            else:
                reasons.append(f"Unsupported rule type: {rule_type}")

        allowed = len(reasons) == 0
        return GateDecision(allowed=allowed, reasons=tuple(reasons), completeness=completeness_result)
                
    @staticmethod
    def _human_required(require_human_approval: bool | str, risk_tier: str) -> bool:
        if isinstance(require_human_approval, bool):
            return require_human_approval
        
        if require_human_approval == "medium_or_high":
            return risk_tier in ("medium", "high")
        
        # Unknow policy strings are treated as "safe default": require approval
        return True