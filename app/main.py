from __future__ import annotations

import json
import sys
from pathlib import Path

from app.engine.audit import AuditLogger, AuditLogEntry
from app.engine.completeness import CompletenessEngine
from app.engine.gates import GateEngine
from app.engine.identity import IdentityError, IdentityValidator
from app.spec_loader import load_spec
from app.engine.state_machine import resolve_transition, TransitionError

def usage() -> None:
    print("Commands:")
    print("  python -m app.main validate-id <EntityType> <IdValue>")
    print('  python -m app.main completeness <EntityType> \'<json>\'')
    print("")
    print("Examples:")
    print("  python -m app.main validate-id Ticket TCKT-1024")
    print(
        "  python -m app.main completeness Ticket "
        "'{\"has_title\": true, \"has_acceptance_criteria\": false, \"has_risk_tier\": true}'"
    )
    print("  python -m app.main transition <EntityType> <FromState> <ToState> <risk_tier> '<json>' [--human-approved]")



def cmd_validate_id(spec_path: Path, entity_type: str, id_value: str) -> int:
    spec = load_spec(spec_path)
    if entity_type not in spec.entities:
        print(f"Unknown entity type: {entity_type}. Known: {', '.join(spec.entities.keys())}")
        return 2

    entity_spec = spec.entities[entity_type]
    validator = IdentityValidator(
        canonical_regex=entity_spec.id.canonical_regex,
        legacy_regexes=entity_spec.id.legacy_regexes,
    )

    try:
        result = validator.validate(entity_type, id_value)
    except IdentityError as e:
        print(f"❌ {e}")
        return 1

    if result.is_legacy:
        print(f"⚠️ Legacy ID detected for {entity_type}: {result.raw_id}")
        return 0

    print(f"✅ Canonical ID OK: {result.canonical_id}")
    return 0


def cmd_completeness(spec_path: Path, entity_type: str, json_payload: str) -> int:
    spec = load_spec(spec_path)
    if entity_type not in spec.entities:
        print(f"Unknown entity type: {entity_type}. Known: {', '.join(spec.entities.keys())}")
        return 2

    try:
        entity_data = json.loads(json_payload)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON payload: {e}")
        return 2

    if not isinstance(entity_data, dict):
        print("❌ JSON payload must be an object/dict.")
        return 2

    checklist = spec.entities[entity_type].checklist
    engine = CompletenessEngine()
    result = engine.compute(checklist=checklist, entity_data=entity_data)

    print(f"Completeness: {result.percent}% ({result.satisfied_items}/{result.total_items})")
    if result.missing_items:
        print("Missing:")
        for m in result.missing_items:
            print(f"  - {m}")
    return 0

def cmd_transition(
    spec_path: Path,
    entity_type: str,
    from_state: str,
    to_state: str,
    risk_tier: str,
    json_payload: str,
    human_approved: bool,
) -> int:
    spec = load_spec(spec_path)
    if entity_type not in spec.entities:
        print(f"Unknown entity type: {entity_type}. Known: {', '.join(spec.entities.keys())}")
        return 2

    if risk_tier not in spec.risk_tiers:
        print(f"Unknown risk tier '{risk_tier}'. Known: {spec.risk_tiers}")
        return 2

    try:
        entity_data = json.loads(json_payload)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON payload: {e}")
        return 2

    entity = spec.entities[entity_type]

    try:
        resolved = resolve_transition(entity, from_state, to_state)
    except TransitionError as e:
        print(f"❌ {e}")
        return 1

    engine = GateEngine()
    decision = engine.evaluate(
        checklist=entity.checklist,
        entity_data=entity_data,
        rules=resolved.gate.rules,
        require_human_approval=resolved.gate.require_human_approval,
        risk_tier=risk_tier,
        human_approved=human_approved,
    )

    # --- Audit Logging ---
    logger = AuditLogger(Path("audit_log.jsonl"))
    entry = AuditLogEntry(
        timestamp=AuditLogger.now_iso(),
        entity_type=entity_type,
        from_state=from_state,
        to_state=to_state,
        risk_tier=risk_tier,
        human_approved=human_approved,
        allowed=decision.allowed,
        reasons=decision.reasons,
        completeness_percent=decision.completeness.percent
        if decision.completeness
        else None
        )
    logger.log(entry)

    if decision.allowed:
        print(f"✅ Transition allowed: {entity_type} {from_state} -> {to_state}")
        if decision.completeness is not None:
            c = decision.completeness
            print(f"Completeness: {c.percent}% ({c.satisfied_items}/{c.total_items})")
        return 0

    print(f"⛔ Transition blocked: {entity_type} {from_state} -> {to_state}")
    for r in decision.reasons:
        print(f"  - {r}")

    if decision.completeness is not None:
        c = decision.completeness
        print(f"Completeness: {c.percent}% ({c.satisfied_items}/{c.total_items})")
        if c.missing_items:
            print("Missing:")
            for m in c.missing_items:
                print(f"  - {m}")

    return 1



def main() -> int:
    if len(sys.argv) < 2:
        usage()
        return 2

    spec_path = Path("guardian_spec.yaml")
    cmd = sys.argv[1]

    if cmd == "validate-id":
        if len(sys.argv) != 4:
            usage()
            return 2
        return cmd_validate_id(spec_path, sys.argv[2], sys.argv[3])

    if cmd == "completeness":
        if len(sys.argv) != 4:
            usage()
            return 2
        return cmd_completeness(spec_path, sys.argv[2], sys.argv[3])
    
    if cmd == "transition":
        # transition Ticket Draft Planned medium '{...}' --human-approved
        if len(sys.argv) < 7:
            usage()
            return 2

        entity_type = sys.argv[2]
        from_state = sys.argv[3]
        to_state = sys.argv[4]
        risk_tier = sys.argv[5]
        json_payload = sys.argv[6]
        human_approved = "--human-approved" in sys.argv[7:]


        return cmd_transition(
            spec_path,
            entity_type,
            from_state,
            to_state,
            risk_tier,
            json_payload,
             human_approved, )


    usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
