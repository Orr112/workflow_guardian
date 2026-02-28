import re

class PatchValidationError(ValueError):
    pass

def sanitize_patch_output(raw: str) -> str:
    t = raw.strip()

    # Remove any markdown fence lines anywhere
    lines = []
    for line in t.splitlines():
        if re.match(r"^\s*```", line):
            continue
        lines.append(line)
    t = "\n".join(lines).strip()

    # MUST contain diff header; slice from first diff header onward
    start = t.find("diff --git ")
    if start == -1:
        raise PatchValidationError("No 'diff --git' found; model did not return a patch.")
    t = t[start:].strip()

    # Ensure newline at end
    if not t.endswith("\n"):
        t += "\n"
    return t


def validate_basic(patch: str) -> None:
    if not patch.startswith("diff --git "):
        raise PatchValidationError("Patch must start with 'diff --git'.")
    if "The changes made in this patch" in patch:
        raise PatchValidationError("Patch contains prose.")
    if "\n--- " not in patch or "\n+++ " not in patch:
        raise PatchValidationError("Patch missing ---/+++ markers.")