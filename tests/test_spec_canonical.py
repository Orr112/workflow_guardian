from app.models import TransitionSpec, GateSpec, GateRule
from app.spec_loader import load_spec
from app.engine.state_machine import resolve_transition
from app.engine.gates import GateEngine


def test_spec_loads_typed_transitions():
    spec = load_spec("guardian_spec.yaml")
    ticket = spec.entities["Ticket"]

    assert isinstance(ticket.transitions[0], TransitionSpec)
    assert ticket.transitions[0].from_state == "Draft"
    assert ticket.transitions[0].to_state == "Planned"

    assert isinstance(ticket.transitions[0].gate, GateSpec)
    # Might be empty for some transitions, but type should still be list
    assert isinstance(ticket.transitions[0].gate.rules, list)

    # If rules exist, they must be GateRule
    for r in ticket.transitions[0].gate.rules:
        assert isinstance(r, GateRule)


def test_resolve_transition_returns_typed_transition():
    spec = load_spec("guardian_spec.yaml")
    ticket = spec.entities["Ticket"]
    resolved = resolve_transition(ticket, "Draft", "Planned")
    assert resolved.transition.from_state == "Draft"
    assert resolved.transition.to_state == "Planned"
    assert isinstance(resolved.transition.gate, GateSpec)


def test_gate_engine_end_to_end_no_dict_drift():
    spec = load_spec("guardian_spec.yaml")
    ticket = spec.entities["Ticket"]

    resolved = resolve_transition(ticket, "ReadyForReview", "Done")
    gate = resolved.transition.gate

    engine = GateEngine()
    decision = engine.evaluate(
        checklist=ticket.checklist,
        entity_data={"has_title": True, "has_acceptance_criteria": True, "has_risk_tier": True},
        rules=gate.rules,
        require_human_approval=gate.require_human_approval,
        risk_tier="medium",
        human_approved=True,
    )

    assert decision.allowed is True
    assert all("Unsupported rule type" not in r for r in decision.reasons)