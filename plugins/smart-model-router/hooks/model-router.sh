#!/bin/bash
# smart-model-router — UserPromptSubmit hook
# Classifies prompts against N configurable tiers and warns or auto-switches.
# Prefix prompt with "~" to bypass entirely.

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(realpath "$0")")/..}"

exec python3 "$PLUGIN_ROOT/hooks/model_router.py"
