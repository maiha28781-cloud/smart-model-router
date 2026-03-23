#!/usr/bin/env python3
"""
smart-model-router — classifier for Claude Code hooks.

Modes:
  (default)     UserPromptSubmit: reads JSON prompt from stdin, outputs systemMessage if routing mismatch
  --session     SessionStart: outputs additionalContext with tier guidance
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

# ─── Default tiers ─────────────────────────────────────────────────────────────
DEFAULT_TIERS = [
    {
        "name": "haiku",
        "models": ["haiku"],
        "switch_to": "haiku",
        "priority": 1,
        "description": "Simple mechanical tasks: git ops, renames, formatting, quick lookups",
        "max_word_count": 60,
        "keywords": [],
        "patterns": [
            r"\bgit\s+(commit|push|pull|status|log|diff|add|stash|branch|merge|rebase|checkout)\b",
            r"\bcommit\b.*\b(change|push|all)\b",
            r"\bpush\s+(to|the|remote|origin)\b",
            r"\brename\b", r"\bmove\s+file\b", r"\bdelete\s+file\b",
            r"\bformat\b", r"\blint\b", r"\bprettier\b", r"\beslint\b",
            r"\bremove\s+(unused|dead)\b", r"\bupdate\s+(version|package)\b",
            r"\badd\s+(import|route|link)\b"
        ]
    },
    {
        "name": "sonnet",
        "models": ["sonnet"],
        "switch_to": "sonnet",
        "priority": 2,
        "description": "Standard implementation: feature work, debugging, code writing, tests",
        "keywords": [],
        "patterns": [
            r"\bbuild\b", r"\bimplement\b", r"\bcreate\b", r"\bfix\b", r"\bdebug\b",
            r"\badd\s+feature\b", r"\bwrite\b", r"\bcomponent\b", r"\bservice\b",
            r"\bdeploy\b", r"\btest\b", r"\bupdate\b", r"\brefactor\b",
            r"\bapi\b", r"\bfunction\b", r"\bstyle\b", r"\bcss\b"
        ]
    },
    {
        "name": "opus",
        "models": ["opus"],
        "switch_to": "opus",
        "priority": 3,
        "description": "Deep analysis: architecture decisions, complex refactors, multi-system reasoning",
        "force_min_word_count": 200,
        "force_question_word_count": 100,
        "keywords": [
            "architect", "architecture", "evaluate", "tradeoff", "trade-off",
            "strategy", "strategic", "compare approaches", "deep dive",
            "redesign", "across the codebase", "multi-system", "complex refactor",
            "analyze", "analysis", "plan mode", "rethink", "high-stakes",
            "critical decision", "security audit", "performance audit"
        ],
        "patterns": []
    }
]

LOG_PATH = os.path.expanduser("~/.claude/logs/smart-model-router.log")
SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")


def log(msg: str):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def load_config() -> dict:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    search_paths = [
        ".claude/smart-model-router.json",
        os.path.expanduser("~/.claude/smart-model-router.json"),
    ]
    if plugin_root:
        search_paths.append(os.path.join(plugin_root, "config", "smart-model-router.json"))
    for path in search_paths:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def find_tier_by_model(model_str: str, tiers: list) -> dict | None:
    for t in tiers:
        model_list = t.get("models", [t["name"]])
        if any(m.lower() in model_str.lower() for m in model_list):
            return t
    return None


def classify(prompt_lower: str, word_count: int, has_question: bool, tiers: list) -> dict | None:
    # Phase 1: heaviest → lightest for force signals
    for t in sorted(tiers, key=lambda x: x.get("priority", 0), reverse=True):
        if t.get("force_min_word_count") and word_count >= t["force_min_word_count"]:
            return t
        if t.get("force_question_word_count") and has_question and word_count >= t["force_question_word_count"]:
            return t
        kws = t.get("keywords", [])
        if kws and any(kw in prompt_lower for kw in kws):
            return t

    # Phase 2: lightest → heaviest for pattern + word count constraints
    for t in sorted(tiers, key=lambda x: x.get("priority", 0)):
        max_wc = t.get("max_word_count")
        min_wc = t.get("min_word_count", 0)
        if max_wc and word_count > max_wc:
            continue
        if word_count < min_wc:
            continue
        kws = t.get("keywords", [])
        pats = t.get("patterns", [])
        if (kws and any(kw in prompt_lower for kw in kws)) or \
           (pats and any(re.search(p, prompt_lower) for p in pats)):
            return t
    return None


def run_session(config: dict, tiers: list):
    """SessionStart: inject tier guidance."""
    action_mode = config.get("action", "warn")
    default_model = config.get("default_model", "sonnet")

    # Get current model
    current_model = "unknown"
    try:
        with open(SETTINGS_PATH) as f:
            s = json.load(f)
        current_model = s.get("model", default_model)
    except Exception:
        pass

    # Find current tier
    current_tier_name = current_model
    for t in sorted(tiers, key=lambda x: x.get("priority", 0)):
        model_list = t.get("models", [t["name"]])
        if any(m.lower() in current_model.lower() for m in model_list):
            current_tier_name = t["name"]
            break

    tier_lines = [f"- **{t['name']}** — {t.get('description', '')}" for t in sorted(tiers, key=lambda x: x.get("priority", 0))]
    subagent_lines = [f"  - `{t['name']}` → {t.get('description', '')}" for t in sorted(tiers, key=lambda x: x.get("priority", 0))]

    context = f"""## Model Routing Rules (smart-model-router)

These rules apply to YOU and to every sub-agent you spawn.

### Available tiers (lightest → heaviest)
{chr(10).join(tier_lines)}

### Current model
`{current_model}` → tier **{current_tier_name}**

### Sub-agent model selection (MANDATORY)
When calling the Agent tool, set the `model` parameter based on task complexity:
{chr(10).join(subagent_lines)}

Never default all sub-agents to the heaviest model. Match the model to the work.

### Override
Prefix any prompt with `~` to bypass classification and keep the current model.

### Customize routing
Edit `~/.claude/smart-model-router.json` (global) or `.claude/smart-model-router.json` (project).
Project config overrides global. Each tier supports: `keywords`, `patterns`, `max_word_count`,
`min_word_count`, `force_min_word_count`, `force_question_word_count`.
Current action mode: `{action_mode}` (warn = recommend only; autoswitch = change settings.json automatically)."""

    output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    print(json.dumps(output))


def run_prompt(config: dict, tiers: list):
    """UserPromptSubmit: classify and route."""
    action_mode = config.get("action", "warn")
    default_model = config.get("default_model", "sonnet")

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = data.get("prompt", "")

    # Override: "~" prefix bypasses routing
    if prompt.lstrip().startswith("~"):
        snippet = prompt[:40].replace("\n", " ") + ("\u2026" if len(prompt) > 40 else "")
        log(f'OVERRIDE prompt="{snippet}"')
        sys.exit(0)

    # Read current model
    settings = {}
    try:
        with open(SETTINGS_PATH) as f:
            settings = json.load(f)
    except Exception:
        sys.exit(0)

    current_model = settings.get("model", default_model).lower()
    if not current_model:
        current_model = default_model

    current_tier = find_tier_by_model(current_model, tiers)
    if current_tier is None:
        sys.exit(0)

    prompt_lower = prompt.lower()
    word_count = len(prompt.split())
    has_question = "?" in prompt
    rec = classify(prompt_lower, word_count, has_question, tiers)

    if rec is None:
        log(f'model={current_model} rec=match action=ALLOW prompt="{prompt[:40]}"')
        sys.exit(0)

    rec_prio = rec.get("priority", 0)
    cur_prio = current_tier.get("priority", 0)

    if rec_prio == cur_prio:
        log(f'model={current_model} rec={rec["name"]} action=ALLOW prompt="{prompt[:40]}"')
        sys.exit(0)

    switch_to = rec.get("switch_to", rec["name"])
    action_label = f'{action_mode.upper()}->{switch_to}'
    log(f'model={current_model} rec={rec["name"]} action={action_label} prompt="{prompt[:40]}"')

    if action_mode == "autoswitch":
        try:
            settings["model"] = switch_to
            with open(SETTINGS_PATH, "w") as f:
                json.dump(settings, f, indent=2)
            msg = f"[smart-model-router] Switched {current_model} \u2192 {switch_to}  (prefix ~ to bypass)"
        except Exception as e:
            msg = f"[smart-model-router] Could not auto-switch to {switch_to}: {e}"
    else:
        direction = "\u2193 down" if rec_prio < cur_prio else "\u2191 up"
        msg = (f"[smart-model-router] {direction} to **{rec['name']}** recommended "
               f"(current: {current_model}). "
               f"Run `/model {switch_to}` to switch, or prefix ~ to bypass.")

    print(json.dumps({"systemMessage": msg}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", action="store_true", help="Run in SessionStart mode")
    args, _ = parser.parse_known_args()

    config = load_config()
    tiers = sorted(config.get("tiers", DEFAULT_TIERS), key=lambda t: t.get("priority", 0))

    if args.session:
        run_session(config, tiers)
    else:
        run_prompt(config, tiers)


if __name__ == "__main__":
    main()
