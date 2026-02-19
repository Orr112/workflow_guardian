import json
from pathlib import Path

from app.engine.audit import AuditLogger, AuditLogEntry


def test_audit_logger_writes_entry(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    logger = AuditLogger(log_path)

    entry = AuditLogEntry(
        timestamp="2024-01-01T00:00:00Z",
        entity_type="Ticket",
        from_state="Draft",
        to_state="Planned",
        risk_tier="low",
        human_approved=True,
        allowed=True,
        reasons=(),
        completeness_percent=100,
    )
    
    logger.log(entry)

    content = log_path.read_text().strip()
    record = json.loads(content)

    assert record["entity_type"] =="Ticket"
    assert record["allowed"] is True
    assert record["completeness_percent"] == 100