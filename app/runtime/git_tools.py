from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class GitSnapshot:
    head: str
    status: str
    diff: str

def _run(repo_root: Path, args: list[str]) -> str:
    proc = subprocess.run(
        args,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{proc.stderr}")
    return proc.stdout

def snapshot(repo_root: Path) -> GitSnapshot:
    head = _run(repo_root, ["git", "rev-parse", "HEAD"]).strip()
    status = _run(repo_root, ["git", "status", "--porcelain"])
    diff = _run(repo_root, ["git", "diff"])
    return GitSnapshot(head=head, status=status, diff=diff)

def apply_path(repo_root: Path, patch_text: str) -> None:
    proc = subprocess.run(
        ["git", "apply", "--whitespace=fix", "-"],
        cwd=str(repo_root),
        input=patch_text,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git apply failed:\n{proc.stderr}")
    