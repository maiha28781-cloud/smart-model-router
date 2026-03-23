#!/bin/bash
# smart-model-router — SessionStart hook
# Reads tier config and injects dynamic model guidance into every session.
# Supports any number of custom tiers beyond haiku/sonnet/opus.

INPUT=$(cat)

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(realpath "$0")")/..}"

python3 "$PLUGIN_ROOT/hooks/model_router.py" --session <<< "$INPUT"

exit 0
