# CLAUDE.md

## Project

A Python 3.12 **agent Pokémon battle harness**: an LLM agent plays real Pokémon Stadium (Gen 1) battles on an N64 emulator — reading the game's RAM to see the board, picking a move, and driving the controller — end to end, with no human hands. The harness owns the turn loop; the agent supplies decisions.

The design is deliberately simple (see `README.md` and `pokemon-battle-harness-plan.md`):

- **The harness owns the turn loop**, not the model — observe → vet → act, one turn at a time.
- **The agent commands intent, not the controller.** It proposes a legal move or switch from the decoded battle state; the harness translates that into button presses. It never touches the emulator directly.
- **A guardrail gate** sits between "agent decides" and "the game acts": every action is vetted (legal move, PP available, don't waste a 0× move, don't switch into a super-effective hit) before it reaches the game. `send_input()` is the only door out of the harness into the emulator.
- **The knowledge base is load-bearing.** RAM stores dex IDs and numbers, not *meaning* — type effectiveness, base stats, and move data ship with the harness and model the **Gen 1 / Stadium ruleset** (single Special stat, category-by-type, crit tied to Speed, Stadium's bug fixes).
- **Backend-swappable.** The same harness runs against any backend, selected in `config.yaml`:
  - **mock** — an in-memory Gen 1 battle engine, no emulator. The default for development and for deterministic, replayable tests. No ROM, no GPU.
  - **project64** — Windows scripting API (`mem.u8` reads, `joypad.set` input). Reads, turn detection, and input in one place.
  - **retroarch** — macOS-native, reads memory over UDP (`READ_CORE_MEMORY`); input via a memory write or a virtual gamepad.

Module map: `world/` (backends: mock + emulator bridges), `kb/` (type chart + base stats + moves), `battle/` (state types, `read_battle` observe, `send_input` act, damage/matchup calc), `guardrails/` (the gate), `harness/` (the turn loop), `agent/` (the player's `decide`).

## Behavioral Rules

### Think Before Coding

State your assumptions before writing code. Surface tradeoffs. Ask before guessing on anything that affects architecture or data. Push back when a simpler approach exists. Never build on an unverified assumption.

### Simplicity First

Write the minimum code that solves the problem. No speculative features. No abstractions for single-use code. If a senior engineer would call it overcomplicated, simplify it.

### Surgical Changes

Touch only what the task requires. Do not improve adjacent code, formatting, comments, or naming that was not part of the ask. Match existing code style exactly.

### Goal-Driven Execution

Define what success looks like before starting. Loop until that definition is met and verified. Do not ask for step-by-step instructions—figure out the path.

### No Model Calls for Deterministic Decisions

Turn detection, legality checks, type effectiveness, damage estimation, retry logic, and threshold decisions belong in code, not LLM calls. The agent decides *intent*; everything mechanical is code. If a rule can be written in code, write it.

### Hard Token Budgets

Every session has a hard token limit: 50,000 tokens. If the limit is reached without a verified solution, write findings to a file and stop. Do not continue past budget.

### One Agent, One Directory

Agents running in parallel work in separate git worktrees. No two agents share a directory. If you need a second agent, run: `git worktree add ../agent-2 [branch-name]`.

### Checkpoint Multi-Step Work

For any task longer than three steps, create or read `PROGRESS.md` in the working directory. Write to it after each step: what was done, what was found, what comes next, what is blocked. If the session ends before completion, the next session reads `PROGRESS.md` first.

### Fail Loudly

If a step fails, stop and report the failure with specifics before continuing. If a test passes but does not cover the actual behavior, say so. Success means verifiable, not reported. Never paper over errors. **A battle that "runs" but picks an illegal move or throws away a turn on a 0× attack is a failure — verify against the resolved battle, not logs.**

### Unique Skill Descriptions

Each skill covers exactly one job. Its description cannot apply to any other skill in the project. If two skills overlap in description, rename before deploying.

### Research and Implementation Are Separate Sessions

Use a subagent for any task that requires reading more than five files or querying more than two sources. Get a structured report. Start a clean session for implementation with only that report as input.

### Scoped Hooks Only

Every hook has an explicit condition (file extension, directory path, or session event). No hook runs unconditionally on every tool call. Batch logging to session end where possible. Run linters/security checks only on changed/relevant files.

## What Not to Touch

- `.env` (credentials for any live emulator bridge / API keys)
- `src/kb/*.json` — the Gen 1 / Stadium ruleset. These define battle correctness and the scoring baseline; changing a value silently invalidates every past result. Fix a wrong value only with a cited source, and update the tests in the same change.

## Success Criteria Default

When in doubt about whether a task is done: Do the tests pass? Does a battle resolve to a winner? Is the output verifiable by something other than Claude's own judgment (a decoded battle state, a resolved battle, a scored win rate)? If no to any of those, it is not done.
