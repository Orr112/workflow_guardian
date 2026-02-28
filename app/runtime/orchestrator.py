from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.runtime.artifact_store import ArtifactStore
from app.runtime.context import ContextBundle, RunContext
from app.runtime.events import AgentEvent
from app.runtime.run_logger import RunLogger


@dataclass(frozen=True)
class PipelineStep:
    stage: str
    agent: str
    inputs: list[str] | None = None

def _read_evidence(run_dir: Path, rel_path: str) -> str:
    p = run_dir / rel_path
    if not p.exists():
        return f"[missing evidence: {rel_path}]"
    return p.read_text(encoding="utf-8")

def new_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = secrets.token_hex(2)
    return f"{ts}_{suffix}"


def load_project_pack(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_pipeline(
    *,
    project_pack_path: Path,
    task: str,
    agent_registry: Dict[str, Any],
) -> Path:
    pack = load_project_pack(project_pack_path)

    project = pack["project"]
    repo_root = Path(pack.get("repo_root", ".")).resolve()

    runs_dir = Path(pack["logging"]["runs_dir"])
    artifacts_dirname = pack["logging"]["artifacts_dirname"]

    run_id = new_run_id()
    run_dir = runs_dir / run_id
    artifacts_dir = run_dir / artifacts_dirname
    log_path = run_dir / "run_log.jsonl"

    logger = RunLogger(log_path)
    store = ArtifactStore(artifacts_dir)

    ctx = RunContext(
        run_id=run_id,
        project=project,
        task=task,
        repo_root=repo_root,
        run_dir=run_dir,
        artifacts_dir=artifacts_dir,
    )

    steps: List[PipelineStep] = [PipelineStep(**s) for s in pack["pipeline"]]

    for step in steps:
        agent_key = step.agent
        if agent_key not in agent_registry:
            event = AgentEvent(
            run_id=ctx.run_id,
            project=ctx.project,
            stage=step.stage,
            agent=agent_key,
            timestamp=logger.now_iso(),
            status="error",
            message=f"Agent not registered: {agent_key}",
            artifacts=list(ctx.artifacts),
        )
            logger.append(event)
            raise RuntimeError(event.message)

        agent = agent_registry[agent_key]

        try:
            # 1) Build allowlisted evidence bundle from PRIOR artifacts
            inputs = step.inputs or ["task"]
            evidence: Dict[str, Any] = {}

            for item in inputs:
                if item == "task":
                    continue

                rel = ctx.evidence_index.get(item)
                if rel is None:
                    rel = f"{artifacts_dirname}/{item}"

                evidence[item] = _read_evidence(run_dir, rel)

            bundle = ContextBundle(
                task=ctx.task,
                repo_root=ctx.repo_root,
                stage=step.stage,
                run_id=ctx.run_id,
                project=ctx.project,
                evidence=evidence,
            )

            # 2) Run agent ONCE
            produced = agent.run(ctx, bundle, store)

            msg = produced.get("message", "ok")
            new_artifacts = produced.get("artifacts", [])
            ctx.artifacts.extend(new_artifacts)

            # 3) Register newly produced artifacts for later stages
            for rel in new_artifacts:
                key = rel.split("/", 1)[-1]  # drop "artifacts/"
                ctx.evidence_index[key] = rel

            # 4) Log
            event = AgentEvent(
                run_id=ctx.run_id,
                project=ctx.project,
                stage=step.stage,
                agent=agent_key,
                timestamp=logger.now_iso(),
                status="ok",
                message=msg,
                artifacts=new_artifacts,
                meta=produced.get("meta"),
            )
            logger.append(event)

        except Exception as e:
            event = AgentEvent(
                run_id=ctx.run_id,
                project=ctx.project,
                stage=step.stage,
                agent=agent_key,
                timestamp=logger.now_iso(),
                status="error",
                message=f"{type(e).__name__}: {e}",
                artifacts=[],
            )
            logger.append(event)
            raise

    return run_dir