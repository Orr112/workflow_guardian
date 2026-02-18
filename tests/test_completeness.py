from app.engine.completeness import CompletenessEngine


def test_completeness_all_true():
    engine = CompletenessEngine()
    checklist = ["a", "b", "c"]
    data = {"a": True, "b": 1, "c": "yes"}
    r = engine.compute(checklist, data)
    assert r.percent == 100
    assert r.satisfied_items == 3
    assert r.missing_items == ()


def test_completeness_some_missing():
    engine = CompletenessEngine()
    checklist = ["has_title", "has_acceptance_criteria", "has_risk_tier"]
    data = {"has_title": True, "has_risk_tier": True}  # acceptance criteria missing
    r = engine.compute(checklist, data)
    assert r.percent == (2 * 100) // 3  # 66
    assert r.satisfied_items == 2
    assert "has_acceptance_criteria" in r.missing_items


def test_completeness_empty_checklist_is_100():
    engine = CompletenessEngine()
    r = engine.compute([], {})
    assert r.percent == 100
    assert r.total_items == 0
