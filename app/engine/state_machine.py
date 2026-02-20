from __future__ import annotations

from dataclasses import dataclass

from app.models import EntitySpec, TransitionSpec


class TransitionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedTransition:
    from_state: str
    to_state: str
    transition: TransitionSpec


def resolve_transition(entity: EntitySpec, from_state: str, to_state: str) -> ResolvedTransition:
    # Validate states exist
    if from_state not in entity.states:
        raise TransitionError(f"Unknown from_state '{from_state}'. Known: {entity.states}")
    if to_state not in entity.states:
        raise TransitionError(f"Unknown to_state '{to_state}'. Known: {entity.states}")

    # Find matching transition spec
    for t in entity.transitions:
        if t.from_state == from_state and t.to_state == to_state:
            return ResolvedTransition(from_state=from_state, to_state=to_state, transition=t)

    raise TransitionError(f"Transition not allowed: {from_state} -> {to_state}")
