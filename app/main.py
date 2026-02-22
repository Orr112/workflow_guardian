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
from app.engine.store import FileEntityStore, EntityRecord, StoreError

from app.llm.reviewer import review_code
from app.llm.testgen import generate_tests


STORE_PATH = Path("entities.json")

def cmd_ai_review(file_path: str) -> int:
    code = Path(file_path).read_text(encoding="utf-8")
    out = review_code(code)
    print(out)
    return 0


def cmd_ai_testgen(file_path: str) -> int:
    code = Path(file_path).read_text(encoding="utf-8")
    out = generate_tests(code)
    print(out)
    return 0



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
    print("  python -m app.main create <EntityType> <EntityId> <risk_tier> '<json>'")
    print("  python -m app.main show <EntityType> <EntityId>")
    print("  python -m app.main apply-transition <EntityType> <EntityId> <ToState> [--human-approved]")
    print("  python -m app.main ai-review <path-to_py_file>")
    print("  python -m app.main ai-testgen <path_to_py_file>")

def cmd_create(spec_path: Path, entity_type: str, entity_id: str, risk_tier: str, json_payload: str) -> int:
    spec = load_spec(spec_path)
    if entity_type not in spec.entities:
        print(f"Unknown entity type: {entity_type}. Known: {', '.join(spec.entities.keys())}")
        return 2
    if risk_tier not in spec.risk_tiers:
        print(f"Unknown risk tier '{risk_tier}'. Known: {spec.risk_tiers}")
        return 2

    entity_spec = spec.entities[entity_type]

    try:
        data = json.loads(json_payload)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON payload: {e}")
        return 2

    # Validate ID
    validator = IdentityValidator(
        canonical_regex=entity_spec.id.canonical_regex,
        legacy_regexes=entity_spec.id.legacy_regexes,
    )
    try:
        id_result = validator.validate(entity_type, entity_id)
        if id_result.is_legacy:
            print(f"⚠️ Legacy ID detected, refusing create until normalized: {entity_id}")
            return 1
    except IdentityError as e:
        print(f"❌ {e}")
        return 1

    store = FileEntityStore(STORE_PATH)
    existing = store.get(entity_type, entity_id)
    if existing is not None:
        print(f"❌ Entity already exists: {entity_type} {entity_id}")
        return 1

    initial_state = entity_spec.states[0]
    rec = EntityRecord(
        entity_type=entity_type,
        entity_id=entity_id,
        risk_tier=risk_tier,
        state=initial_state,
        data=data,
    )
    store.upsert(rec)
    print(f"✅ Created {entity_type} {entity_id} in state {initial_state}")
    return 0


def cmd_show(spec_path: Path, entity_type: str, entity_id: str) -> int:
    store = FileEntityStore(STORE_PATH)
    rec = store.get(entity_type, entity_id)
    if rec is None:
        print(f"❌ Not found: {entity_type} {entity_id}")
        return 1
    
    print(f"{rec.entity_type} {rec.entity_id}")
    print(f"Risk: {rec.risk_tier}")
    print(f"State: {rec.state}")
    print(json.dumps(rec.data, indent=2, sort_keys=True))
    return 0



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
        gate = resolved.transition.gate
    except TransitionError as e:
        print(f"❌ {e}")
        return 1

    engine = GateEngine()
    decision = engine.evaluate(
        checklist=entity.checklist,
        entity_data=entity_data,
        rules=gate.rules,
        require_human_approval=gate.require_human_approval,
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


def cmd_apply_transition(
    spec_path: Path,
    entity_type: str,
    entity_id: str,
    to_state: str,
    human_approved: bool,
) -> int:
    spec = load_spec(spec_path)
    if entity_type not in spec.entities:
        print(f"Unknown entity type: {entity_type}. Known: {', '.join(spec.entities.keys())}")
        return 2

    store = FileEntityStore(STORE_PATH)
    try:
        rec = store.require(entity_type, entity_id)
    except StoreError as e:
        print(f"❌ {e}")
        return 1

    entity_spec = spec.entities[entity_type]

    from_state = rec.state
    risk_tier = rec.risk_tier

    try:
        resolved = resolve_transition(entity_spec, from_state, to_state)
    except TransitionError as e:
        print(f"❌ {e}")
        return 1

    engine = GateEngine()
    decision = engine.evaluate(
        checklist=entity_spec.checklist,
        entity_data=rec.data,
        rules=resolved.gate.rules,
        require_human_approval=resolved.gate.require_human_approval,
        risk_tier=risk_tier,
        human_approved=human_approved,
    )

    # Audit
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
        completeness_percent=decision.completeness.percent if decision.completeness else None,
    )
    logger.log(entry)

    if not decision.allowed:
        print(f"⛔ Transition blocked: {entity_type} {entity_id} {from_state} -> {to_state}")
        for r in decision.reasons:
            print(f"  - {r}")
        return 1

    # Apply state update
    rec.state = to_state
    store.upsert(rec)
    print(f"✅ Transition applied: {entity_type} {entity_id} {from_state} -> {to_state}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        usage()
        return 2

    spec_path = Path("guardian_spec.yaml")
    cmd = sys.argv[1]

    if cmd == "ai-review":
        if len(sys.argv) != 3:
            usage()
            return 2
        return cmd_ai_review(sys.argv[2])

    if cmd == "ai-testgen":
        if len(sys.argv) != 3:
            usage()
            return
        return cmd_ai_testgen(sys.argv[2])

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
    
    if cmd == "create":
        if len(sys.argv) != 6:
            usage()
            return 2
        return cmd_create(spec_path, sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])

    if cmd == "show":
        if len(sys.argv) != 4:
            usage()
            return 2
        return cmd_show(spec_path, sys.argv[2], sys.argv[3])

    if cmd == "apply-transition":
        if len(sys.argv) < 5:
            usage()
            return 2
        human_approved = "--human-approved" in sys.argv[5:]
        return cmd_apply_transition(spec_path, sys.argv[2], sys.argv[3], sys.argv[4], human_approved)

    
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
