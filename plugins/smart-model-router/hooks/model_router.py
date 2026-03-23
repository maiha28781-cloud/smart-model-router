#!/usr/bin/env python3
"""
smart-model-router — classifier for Claude Code hooks.

Inspired by:
  - tzachbon/claude-model-router-hook (config walk-up, extend/replace mode, safe_regex, system-prompt skip)
  - coyvalyss1/model-matchmaker (NDJSON structured logging, completion tracking)

Modes:
  (default)     UserPromptSubmit: reads JSON prompt from stdin, outputs systemMessage if routing mismatch
  --session     SessionStart: outputs additionalContext with tier guidance
"""
import argparse
import json
import os
import pathlib
import re
import sys
from datetime import datetime

# ─── Defaults ────────────────────────────────────────────────────────────────
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

LOG_PATH = os.path.expanduser("~/.claude/logs/smart-model-router.ndjson")
SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")


# ─── Logging (NDJSON) ────────────────────────────────────────────────────────
def log_event(event: str, **fields):
    """Append a structured NDJSON line to the log file."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        entry = {"event": event, "ts": datetime.now().isoformat(), **fields}
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# ─── Config loading (global + project walk-up, inspired by tzachbon) ─────────
def load_config(cwd=None) -> dict:
    config = {}
    search_paths = [
        pathlib.Path.home() / ".claude" / "smart-model-router.json",
    ]
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        search_paths.append(pathlib.Path(plugin_root) / "config" / "smart-model-router.json")

    for p in search_paths:
        if p.exists():
            try:
                with open(p) as f:
                    config = json.load(f)
            except Exception:
                pass
            break

    # Walk up from CWD to find project-level override (inspired by tzachbon)
    search_root = pathlib.Path(cwd) if cwd else pathlib.Path.cwd()
    for parent in [search_root, *search_root.parents]:
        project_cfg = parent / ".claude" / "smart-model-router.json"
        if project_cfg.exists():
            try:
                with open(project_cfg) as f:
                    proj = json.load(f)
                for key in proj:
                    if key == "$schema":
                        continue
                    if isinstance(proj[key], dict) and isinstance(config.get(key), dict):
                        config[key] = {**config[key], **proj[key]}
                    else:
                        config[key] = proj[key]
            except Exception:
                pass
            break

    return config


# ─── Tier keyword/pattern resolution (extend/replace, inspired by tzachbon) ──
def resolve_list(tier_cfg: dict, field: str, defaults: list) -> list:
    mode = tier_cfg.get("mode", "extend")
    if mode == "replace":
        return list(tier_cfg.get(field, []))
    result = list(defaults)
    result.extend(tier_cfg.get(field, []))
    for item in tier_cfg.get(f"remove_{field}", []):
        if item in result:
            result.remove(item)
    return result


# ─── Safe regex (inspired by tzachbon) ───────────────────────────────────────
def safe_regex_match(patterns: list, text: str) -> bool:
    for p in patterns:
        try:
            if re.search(p, text):
                return True
        except re.error:
            pass
    return False


# ─── Helpers ─────────────────────────────────────────────────────────────────
def find_tier_by_model(model_str: str, tiers: list) -> dict | None:
    for t in tiers:
        if any(m.lower() in model_str.lower() for m in t.get("models", [t["name"]])):
            return t
    return None


def classify(prompt_lower: str, word_count: int, has_question: bool,
             tiers: list, raw_tier_cfgs: dict) -> dict | None:
    # Phase 1: heaviest → lightest for force/keyword signals
    for t in sorted(tiers, key=lambda x: x.get("priority", 0), reverse=True):
        tcfg = raw_tier_cfgs.get(t["name"], {})
        if t.get("force_min_word_count") and word_count >= t["force_min_word_count"]:
            return t
        if t.get("force_question_word_count") and has_question and word_count >= t["force_question_word_count"]:
            return t
        kws = resolve_list(tcfg, "keywords", t.get("keywords", []))
        if kws and any(kw in prompt_lower for kw in kws):
            return t

    # Phase 2: lightest → heaviest for pattern + word-count constraints
    for t in sorted(tiers, key=lambda x: x.get("priority", 0)):
        tcfg = raw_tier_cfgs.get(t["name"], {})
        max_wc = t.get("max_word_count")
        min_wc = t.get("min_word_count", 0)
        if max_wc and word_count > max_wc:
            continue
        if word_count < min_wc:
            continue
        pats = resolve_list(tcfg, "patterns", t.get("patterns", []))
        kws = resolve_list(tcfg, "keywords", t.get("keywords", []))
        if (kws and any(kw in prompt_lower for kw in kws)) or safe_regex_match(pats, prompt_lower):
            return t
    return None


# ─── Session mode ─────────────────────────────────────────────────────────────
def run_session(config: dict, tiers: list):
    action_mode = config.get("action", "warn")
    current_model = "unknown"
    try:
        with open(SETTINGS_PATH) as f:
            current_model = json.load(f).get("model", "sonnet")
    except Exception:
        pass

    current_tier_name = current_model
    for t in sorted(tiers, key=lambda x: x.get("priority", 0)):
        if any(m.lower() in current_model.lower() for m in t.get("models", [t["name"]])):
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
Project config overrides global. Tier supports: `keywords`, `patterns`, `max_word_count`,
`min_word_count`, `force_min_word_count`, `force_question_word_count`, `mode` (extend/replace),
`remove_keywords`, `remove_patterns`.
Current action mode: `{action_mode}` (warn = recommend only; autoswitch = change settings.json automatically)."""

    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))


# ─── Prompt mode ──────────────────────────────────────────────────────────────
def run_prompt(config: dict, tiers: list):
    action_mode = config.get("action", "warn")
    default_model = config.get("default_model", "sonnet")
    raw_tier_cfgs = {t["name"]: config.get(t["name"], {}) for t in tiers}

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = data.get("prompt", "")
    conversation_id = data.get("conversation_id", "")

    # Skip system/XML prompts (inspired by tzachbon)
    if prompt.lstrip().startswith("<"):
        sys.exit(0)

    # Override: "~" prefix bypasses routing
    if prompt.lstrip().startswith("~"):
        log_event("recommendation", model="bypass", recommendation="bypass",
                  action="OVERRIDE", prompt=prompt[:60], conversation_id=conversation_id)
        sys.exit(0)

    settings = {}
    try:
        with open(SETTINGS_PATH) as f:
            settings = json.load(f)
    except Exception:
        sys.exit(0)

    current_model = settings.get("model", default_model).lower() or default_model
    current_tier = find_tier_by_model(current_model, tiers)
    if current_tier is None:
        sys.exit(0)

    prompt_lower = prompt.lower()
    word_count = len(prompt.split())
    has_question = "?" in prompt
    rec = classify(prompt_lower, word_count, has_question, tiers, raw_tier_cfgs)

    if rec is None:
        log_event("recommendation", model=current_model, recommendation="match",
                  action="ALLOW", prompt=prompt[:60], conversation_id=conversation_id)
        sys.exit(0)

    rec_prio = rec.get("priority", 0)
    cur_prio = current_tier.get("priority", 0)

    if rec_prio == cur_prio:
        log_event("recommendation", model=current_model, recommendation=rec["name"],
                  action="ALLOW", prompt=prompt[:60], conversation_id=conversation_id)
        sys.exit(0)

    switch_to = rec.get("switch_to", rec["name"])
    log_event("recommendation", model=current_model, recommendation=rec["name"],
              action="BLOCK", switch_to=switch_to, prompt=prompt[:60], conversation_id=conversation_id)

    if action_mode == "autoswitch":
        try:
            settings["model"] = switch_to
            with open(SETTINGS_PATH, "w") as f:
                json.dump(settings, f, indent=2)
            msg = f"[smart-model-router] Switched {current_model} → {switch_to}  (prefix ~ to bypass)"
        except Exception as e:
            msg = f"[smart-model-router] Could not auto-switch to {switch_to}: {e}"
    else:
        direction = "↓ down" if rec_prio < cur_prio else "↑ up"
        msg = (f"[smart-model-router] {direction} to **{rec['name']}** recommended "
               f"(current: {current_model}). "
               f"Run `/model {switch_to}` to switch, or prefix ~ to bypass.")

    print(json.dumps({"systemMessage": msg}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", action="store_true")
    args, _ = parser.parse_known_args()
    config = load_config()
    tiers = sorted(config.get("tiers", DEFAULT_TIERS), key=lambda t: t.get("priority", 0))
    if args.session:
        run_session(config, tiers)
    else:
        run_prompt(config, tiers)


if __name__ == "__main__":
    main()
