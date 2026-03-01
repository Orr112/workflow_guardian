from app.engine.gates import GateEngine
from app.models import GateRule


def test_blocks_when_completeness_below_threshold():
    engine = GateEngine()
    rules = [GateRule(type="completeness_min", percent=100)]
    checklist = ["a", "b"]
    data = {"a": True, "b": False}

    decision = engine.evaluate(
        checklist=checklist,
        entity_data=data,
        rules=rules,
        require_human_approval=False,
        risk_tier="low",
        human_approved=False,
    )
    assert decision.allowed is False
    assert any("below required" in r for r in decision.reasons)


def test_requires_human_approval_medium_or_high():
    engine = GateEngine()
    rules = []
    checklist = ["a"]
    data = {"a": True}

    decision = engine.evaluate(
        checklist=checklist,
        entity_data=data,
        rules=rules,
        require_human_approval="medium_or_high",
        risk_tier="medium",
        human_approved=False,
    )
    assert decision.allowed is False
    assert "Human approval required" in decision.reasons[0]


def test_allows_low_risk_without_human_when_policy_medium_or_high():
    engine = GateEngine()
    rules = []
    checklist = ["a"]
    data = {"a": True}

    decision = engine.evaluate(
        checklist=checklist,
        entity_data=data,
        rules=rules,
        require_human_approval="medium_or_high",
        risk_tier="low",
        human_approved=False,
    )
    assert decision.allowed is True


def test_always_blocks_with_reason():
    engine = GateEngine()
    rules = [GateRule(type="always_block")]
    checklist = ["a", "b"]
    data = {"a": True, "b": True}

    decision = engine.evaluate(
        checklist=checklist,
        entity_data=data,
        rules=rules,
        require_human_approval=False,
        risk_tier="low",
        human_approved=False,
    )
    assert decision.allowed is False
    assert "Rule always_block triggered." in decision.reasons[0]
