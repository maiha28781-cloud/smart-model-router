#!/usr/bin/env bash
# smart-model-router — manual install script
# Use this only if you prefer not to install via `claude plugin`.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SRC="$SCRIPT_DIR/plugins/smart-model-router"
HOOKS_DIR="$HOME/.claude/hooks"
CONFIG_DST="$HOME/.claude/smart-model-router.json"
SETTINGS="$HOME/.claude/settings.json"

echo "[smart-model-router] Installing hooks..."
mkdir -p "$HOOKS_DIR"
cp "$PLUGIN_SRC/hooks/session-init.sh" "$HOOKS_DIR/smr-session-init.sh"
cp "$PLUGIN_SRC/hooks/model-router.sh" "$HOOKS_DIR/smr-model-router.sh"
cp "$PLUGIN_SRC/hooks/model_router.py" "$HOOKS_DIR/smr-model_router.py"
chmod +x "$HOOKS_DIR/smr-session-init.sh" "$HOOKS_DIR/smr-model-router.sh"

# Fix PLUGIN_ROOT reference in scripts
sed -i "s|\${CLAUDE_PLUGIN_ROOT:-\$(dirname \"\$(realpath \"\$0\")\")/.."}|$HOOKS_DIR|g" \
  "$HOOKS_DIR/smr-session-init.sh" "$HOOKS_DIR/smr-model-router.sh" 2>/dev/null || true

if [ ! -f "$CONFIG_DST" ]; then
  cp "$PLUGIN_SRC/config/smart-model-router.json" "$CONFIG_DST"
  echo "[smart-model-router] Default config copied to $CONFIG_DST"
fi

echo "[smart-model-router] Done! Restart Claude Code to activate."
echo "Tip: Edit $CONFIG_DST to customize tiers."
