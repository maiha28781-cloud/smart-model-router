#!/bin/bash
# smart-model-router — Stop hook
# Logs task completion status for accuracy analysis.
# Inspired by coyvalyss1/model-matchmaker.

INPUT=$(cat)

echo "$INPUT" | python3 -c '
import json, sys, os
from datetime import datetime

try:
    data = json.load(sys.stdin)
except:
    sys.exit(0)

status = data.get("stop_hook_active", False)
conversation_id = data.get("conversation_id", "")
model = ""
try:
    settings_path = os.path.expanduser("~/.claude/settings.json")
    with open(settings_path) as f:
        model = json.load(f).get("model", "").lower()
except Exception:
    pass

try:
    log_dir = os.path.expanduser("~/.claude/logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "smart-model-router.ndjson")
    entry = {
        "event": "completion",
        "ts": datetime.now().isoformat(),
        "conversation_id": conversation_id,
        "model": model,
        "status": "completed",
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
except Exception:
    pass
' > /dev/null 2>&1

echo '{}'
exit 0
