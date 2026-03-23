#!/bin/bash
# smart-model-router Analytics
# Parses NDJSON logs and prints accuracy/usage metrics.
# Inspired by coyvalyss1/model-matchmaker.
#
# Usage:
#   ./analytics.sh                  # all-time summary
#   ./analytics.sh --days 7         # last 7 days
#   ./analytics.sh --json           # machine-readable JSON
#   ./analytics.sh --json --days 7

LOG_PATH="${HOME}/.claude/logs/smart-model-router.ndjson"

if [ ! -f "$LOG_PATH" ]; then
    echo "No analytics data found at $LOG_PATH"
    echo "Use smart-model-router for a while and data will appear here."
    exit 0
fi

DAYS=0
JSON_OUT=false
for arg in "$@"; do
    case $arg in
        --json) JSON_OUT=true ;;
        --days) shift ;;
        [0-9]*) DAYS=$arg ;;
    esac
done

python3 << PYEOF
import json, sys, os
from datetime import datetime, timedelta
from collections import Counter

log_path = "$LOG_PATH"
days_filter = int("$DAYS")
json_out = $([[ "$JSON_OUT" == "true" ]] && echo "True" || echo "False")

recs = []
completions = []
cutoff = datetime.now() - timedelta(days=days_filter) if days_filter > 0 else None

with open(log_path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if cutoff:
            try:
                if datetime.fromisoformat(entry.get("ts", "")) < cutoff:
                    continue
            except Exception:
                continue
        if entry.get("event") == "recommendation":
            recs.append(entry)
        elif entry.get("event") == "completion":
            completions.append(entry)

total = len(recs)
if total == 0:
    msg = "No recommendation data yet." if not json_out else json.dumps({"error": "no data"})
    print(msg)
    sys.exit(0)

actions = Counter(r["action"] for r in recs)
rec_types = Counter(r["recommendation"] for r in recs)
models = Counter(r["model"] for r in recs)

override_rate = actions["OVERRIDE"] / total * 100
block_rate = actions["BLOCK"] / total * 100
allow_rate = actions["ALLOW"] / total * 100

block_flows = Counter(f"{r['model']} → {r['recommendation']}" for r in recs if r["action"] == "BLOCK")

if json_out:
    print(json.dumps({
        "total_recommendations": total,
        "period_days": days_filter or "all",
        "actions": dict(actions),
        "recommendations": dict(rec_types),
        "models_used": dict(models),
        "rates": {
            "override_pct": round(override_rate, 1),
            "block_pct": round(block_rate, 1),
            "allow_pct": round(allow_rate, 1),
        },
        "block_flows": dict(block_flows),
        "completions": len(completions),
    }, indent=2))
else:
    period = f" (last {days_filter}d)" if days_filter else ""
    print("=" * 50)
    print(f"  SMART MODEL ROUTER ANALYTICS{period}")
    print("=" * 50)
    print(f"  Total prompts classified : {total}")
    print(f"  Blocked (wrong model)    : {actions['BLOCK']} ({block_rate:.1f}%)")
    print(f"  Allowed (correct model)  : {actions['ALLOW']} ({allow_rate:.1f}%)")
    print(f"  Overridden (~)           : {actions['OVERRIDE']} ({override_rate:.1f}%)")
    print()
    print("  Recommendation breakdown:")
    for rec, count in rec_types.most_common():
        print(f"    {rec:<12} {count:>5}  ({count/total*100:.1f}%)")
    print()
    print("  Model usage when classified:")
    for m, count in models.most_common():
        print(f"    {m:<20} {count:>5}")
    if block_flows:
        print()
        print("  Top mismatch flows (blocked):")
        for flow, count in block_flows.most_common(5):
            print(f"    {flow:<30} {count:>4}x")
    print()
    print(f"  Completions logged       : {len(completions)}")
    print("=" * 50)
PYEOF
