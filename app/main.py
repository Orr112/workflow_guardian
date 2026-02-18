from __future__ import annotations

import json
import sys
from pathlib import Path

from app.engine.completeness import CompletenessEngine
from app.engine.identity import IdentityError, IdentityValidator
from app.spec_loader import load_spec


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

    usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
