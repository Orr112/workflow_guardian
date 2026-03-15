#!/usr/bin/env bash
set -euo pipefail

PROMPT_FILE=$1

export ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-claude-sonnet-4-6}
export ANTHROPIC_MAX_TOKENS=${ANTHROPIC_MAX_TOKENS:-8000}

python -m app.main run-pipeline \
projects/rate_comparison/project_rate_compare.yaml \
"$(cat "$PROMPT_FILE")"