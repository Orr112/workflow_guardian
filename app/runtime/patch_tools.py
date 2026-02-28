import re
from typing import Iterable

class PatchValidationError(ValueError):
    pass

_DIFF_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)

def patch_touched_paths(patch: str) -> list[str]:
    paths: list[str] = []
    for m in _DIFF_RE.finditer(patch):
        a_path, b_path = m.group(1), m.group(2)
        # usually same; take b_path
        paths.append(b_path)
    return paths

def validate_allowed_paths(patch: str, allowed: Iterable[str]) -> None:
    allowed_set = set(allowed)
    touched = patch_touched_paths(patch)
    if not touched:
        raise PatchValidationError("Patch contains no diff --git sections.")
    bad = [p for p in touched if p not in allowed_set]
    if bad:
        raise PatchValidationError(f"Patch touches disallowed paths: {bad}")


def validate_basic(patch: str) -> None:
    if not patch.startswith("diff --git "):
        raise PatchValidationError("Patch must start with 'diff --git'.")
    if "The changes made in this patch" in patch:
        raise PatchValidationError("Patch contains prose.")
    if "\n--- " not in patch or "\n+++ " not in patch:
        raise PatchValidationError("Patch missing ---/+++ markers.")