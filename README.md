# smart-model-router

> Auto model-switching plugin for Claude Code — routes prompts to the right tier to save API tokens.

## What it does

Every prompt you type is silently classified and compared against your current model:

- `git commit all changes` → recommends **haiku** (cheap, fast)
- `implement the auth API endpoint` → recommends **sonnet** (default)
- `redesign the entire caching architecture` → recommends **opus** (deep reasoning)

No API calls. Zero latency. Fully configurable.

## Install via plugin (recommended)

```bash
claude plugin marketplace add maiha28781-cloud/smart-model-router
claude plugin install smart-model-router@maiha28781-cloud
```

Restart Claude Code to activate.

## Manual install

```bash
git clone https://github.com/maiha28781-cloud/smart-model-router.git
cd smart-model-router
bash install.sh
```

## Configuration

Create `~/.claude/smart-model-router.json` (global) or `.claude/smart-model-router.json` (project-level, overrides global):

```json
{
  "action": "warn",
  "tiers": [
    {
      "name": "haiku",
      "models": ["haiku"],
      "switch_to": "haiku",
      "priority": 1,
      "description": "Simple mechanical tasks",
      "max_word_count": 60,
      "patterns": ["\\bgit\\s+(status|log|diff)\\b"]
    },
    {
      "name": "sonnet",
      "models": ["sonnet"],
      "switch_to": "sonnet",
      "priority": 2,
      "description": "Standard implementation",
      "is_default": true,
      "patterns": ["\\bimplement\\b", "\\bfix\\b"]
    },
    {
      "name": "opus",
      "models": ["opus"],
      "switch_to": "opus",
      "priority": 3,
      "description": "Deep analysis",
      "force_min_word_count": 200,
      "keywords": ["architecture", "analyze", "strategy"]
    }
  ]
}
```

### Add a custom model tier

```json
{
  "name": "my-model",
  "models": ["my-model-id"],
  "switch_to": "my-model-id",
  "priority": 4,
  "description": "My specialized model",
  "keywords": ["ultra complex", "full codebase audit"],
  "patterns": []
}
```

### Extend or replace default keywords/patterns per tier

```json
{
  "opus": {
    "mode": "extend",
    "keywords": ["my-custom-signal"],
    "remove_keywords": ["rethink"]
  },
  "haiku": {
    "mode": "replace",
    "patterns": ["\\bgit status\\b"]
  }
}
```

> `mode: extend` (default) — adds to built-in keywords/patterns, supports `remove_keywords` / `remove_patterns`  
> `mode: replace` — discards built-ins entirely, uses only your list

## Config options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `warn` \| `autoswitch` | `warn` | `warn` = recommend only; `autoswitch` = change `settings.json` automatically |
| `default_model` | string | `sonnet` | Assumed model when `settings.json` has no `model` field |
| `tiers` | array | see defaults | List of model tiers |

### Tier options

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name |
| `models` | string[] | Substrings matched against current model |
| `switch_to` | string | Value written to `settings.json` on autoswitch |
| `priority` | int | Tier weight (lower = lighter). Must be unique. |
| `mode` | `extend` \| `replace` | Whether to extend or replace default keywords/patterns |
| `keywords` | string[] | Case-insensitive keywords matched against prompt |
| `remove_keywords` | string[] | Remove specific defaults (extend mode only) |
| `patterns` | string[] | Python regex patterns matched against prompt |
| `remove_patterns` | string[] | Remove specific default patterns (extend mode only) |
| `max_word_count` | int | Only match if prompt is shorter than this |
| `min_word_count` | int | Only match if prompt is longer than this |
| `force_min_word_count` | int | Force this tier if prompt exceeds N words |
| `force_question_word_count` | int | Force this tier if prompt is a long question |

## Override

Prefix any prompt with `~` to skip classification entirely:

```
~ do this with whatever model i'm on
```

## Analytics

All routing decisions are logged as structured NDJSON at `~/.claude/logs/smart-model-router.ndjson`.

```bash
# All-time summary
bash ~/.claude/plugins/cache/maiha28781-cloud/smart-model-router/*/plugins/smart-model-router/hooks/analytics.sh

# Last 7 days
bash analytics.sh --days 7

# Machine-readable JSON
bash analytics.sh --json
```

Example output:
```
==================================================
  SMART MODEL ROUTER ANALYTICS
==================================================
  Total prompts classified : 142
  Blocked (wrong model)    : 38 (26.8%)
  Allowed (correct model)  : 97 (68.3%)
  Overridden (~)           : 7 (4.9%)

  Recommendation breakdown:
    sonnet          82  (57.7%)
    haiku           41  (28.9%)
    opus            19  (13.4%)

  Top mismatch flows (blocked):
    sonnet → haiku                  22x
    sonnet → opus                   12x
    opus → sonnet                    4x
==================================================
```

## Logs

```bash
# Structured NDJSON (for scripting)
tail -f ~/.claude/logs/smart-model-router.ndjson | python3 -m json.tool
```

## Acknowledgements

Inspired by and borrows ideas from:
- **[tzachbon/claude-model-router-hook](https://github.com/tzachbon/claude-model-router-hook)** — plugin structure, config walk-up, extend/replace mode, safe regex
- **[coyvalyss1/model-matchmaker](https://github.com/coyvalyss1/model-matchmaker)** — NDJSON logging, analytics dashboard, completion tracking

## License

MIT
