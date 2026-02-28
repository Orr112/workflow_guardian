import re

class PatchValidationError(ValueError):
    pass

def sanitize_patch_output(raw: str) -> str:
    t = raw.strip()

    # Remove any markdown fences, including ```diff / ```patch / plain ```
    # Do this line-wise so we don't accidentally delete valid diff content.
    lines = t.splitlines()
    cleaned_lines = []
    for line in lines:
        if re.match(r"^\s*```", line):
            continue
        cleaned_lines.append(line)
    t = "\n".join(cleaned_lines).strip()

    # Extract from first diff header onward
    idx = t.find("diff --git ")
    if idx == -1:
        raise PatchValidationError("No 'diff --git' header found in model output.")
    t = t[idx:].strip()

    # Ensure newline at end
    if not t.endswith("\n"):
        t += "\n"
    return t

def validate_basic(patch: str) -> None:
    if "```" in patch:
        raise PatchValidationError("Patch still contains markdown fences (```)")
    if not patch.startswith("diff --git "):
        raise PatchValidationError("Patch does not start with 'diff --git'")
    if "\n--- " not in patch or "\n+++ " not in patch:
        raise PatchValidationError("Patch missing ---/+++ file markers")