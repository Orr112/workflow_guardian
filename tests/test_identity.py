import pytest

from app.engine.identity import IdentityValidator, IdentityError

def test_canonical_id_ok():
    v = IdentityValidator(r"^TCKT-[0-9]+$", [r"^TICKET_[0-9]+$", r"^T-[0-9]+$"])
    r = v.validate("Ticket", "TCKT-1024")
    assert r.is_legacy is False
    assert r.canonical_id == "TCKT-1024"

def test_legacy_id_detected():
    v = IdentityValidator(r"^TCKT-[0-9]+$", [r"^TICKET_[0-9]+$", r"^T-[0-9]+$"])
    r = v.validate("Ticket", "TICKET_1024")
    assert r.is_legacy is True
    assert r.canonical_id is None

def test_invalid_id_rejected():
    v = IdentityValidator(r"^TCKT-[0-9]+$", [r"^TICKET_[0-9]+$", r"^T-[0-9]+$"])
    with pytest.raises(IdentityError):
        v.validate("Ticket", "ABC-999")