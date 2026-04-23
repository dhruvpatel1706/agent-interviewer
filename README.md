# agent-interviewer

**Practice mock interviews in your terminal. Four specialized Claude personas. Honest per-dimension feedback at the end.**

Each persona is a separate system prompt with its own evaluation rubric. The interviewer plays its role during the session (no grading mid-interview — just probing questions). After you type `/end`, a separate feedback agent reads the whole transcript and returns a structured critique: a 1-5 score per dimension, a concrete observation grounded in the transcript, a specific suggestion, and an overall recommendation.

```
$ agent-interviewer start --type system-design
╭──────────────────────────────────────────────────────────╮
│ System design interviewer                                │
│ Type /end to finish, /save to flush                      │
│ Session id: a3f9e2c1b4                                   │
╰──────────────────────────────────────────────────────────╯

Interviewer: Let's design a URL shortener. Assume 100M URLs over 5 years,
peak read of 1000 req/s, 10:1 read-to-write ratio. Start with the API
surface and the single-node design — we'll scale from there.

You: > /end

                              Per-dimension scores
 ┌───────────────────────────────┬────────────┬────────────────────────┬─────────────────────┐
 │ dimension                     │ score      │ observation            │ suggestion          │
 ├───────────────────────────────┼────────────┼────────────────────────┼─────────────────────┤
 │ requirements clarification    │ ████░ 4/5  │ Asked about durability │ Also pin down the   │
 │                               │            │ and latency up front   │ write throughput    │
 │ high-level architecture       │ ███░░ 3/5  │ ...                    │ ...                 │
 │ data model and storage choice │ ████░ 4/5  │ ...                    │ ...                 │
 │ scaling bottlenecks           │ ██░░░ 2/5  │ Skipped over hashing   │ Work through a      │
 │                               │            │ collision handling     │ birthday-paradox    │
 │                               │            │                        │ estimate next time  │
 │ tradeoff articulation         │ ███░░ 3/5  │ ...                    │ ...                 │
 └───────────────────────────────┴────────────┴────────────────────────┴─────────────────────┘

Strengths:
  • Drove the conversation — didn't wait to be prompted
  • Asked for concrete numbers before committing to storage choice

Growth areas:
  • Dedicate explicit time to collision analysis for base62 hashing
  • Calculate storage footprint before choosing between SQL and a KV store

Mock recommendation: borderline
```

---

## Personas

| Key | Evaluates |
| --- | --- |
| `behavioral` | specificity, STAR structure, ownership, self-reflection, impact |
| `system-design` | requirements clarification, high-level architecture, data model, scaling, tradeoffs |
| `coding` | problem understanding, approach-before-code, correctness, edge cases, complexity |
| `case` | framing, structure, quantitative estimation, prioritization, recommendation clarity |

Each persona is defined by a system prompt + a fixed set of evaluation dimensions. The dimensions are what the feedback agent scores you against — they're passed into the feedback model so scoring is consistent across sessions.

## Install

```bash
git clone https://github.com/dhruvpatel1706/agent-interviewer.git
cd agent-interviewer
pip install -e .
```

## Configure

```bash
cp .env.example .env
# add ANTHROPIC_API_KEY
```

## Use

```bash
# List personas
agent-interviewer personas

# Start a mock interview
agent-interviewer start --type coding
agent-interviewer start --type behavioral
agent-interviewer start --type system-design
agent-interviewer start --type case

# Skip the end-of-session feedback (get it later)
agent-interviewer start --type case --no-feedback

# Generate feedback for a previously-saved session
agent-interviewer feedback a3f9e2c1b4

# Resume a session
agent-interviewer resume a3f9e2c1b4
```

Inside a session: `/end` to finish, `/save` is a no-op (everything is saved incrementally as JSONL).

Session transcripts land in `~/.agent-interviewer/sessions/` as JSONL (one turn per line) plus a `.feedback.json` sidecar once you've run the feedback agent.

## How it works

Two separate Claude calls, each with its own cached system prompt:

1. **Interview loop** (`session.py`) — builds a Claude conversation with the persona's prompt as system. The `cache_control: ephemeral` marker on the system prompt means every subsequent turn in the same session reuses the cached prefix, which is cheaper and faster. Uses adaptive thinking so the interviewer can deliberate more on harder turns without a fixed budget.

2. **Feedback agent** (`feedback.py`) — reads the full transcript + the persona's evaluation dimensions, returns a validated `Feedback` model via `client.messages.parse()` with a Pydantic schema. This separation matters — the interviewer doesn't hedge mid-interview because it knows the evaluator is a different prompt.

State is persisted as JSONL so sessions are resumable, inspectable (you can grep your own transcripts), and survive crashes. The feedback is saved as a sidecar JSON so you can view multiple critiques of the same session without re-running.

## Design choices

- **Structured feedback via `messages.parse`.** The `Feedback` schema forces the model to separate strengths from growth areas, score every dimension, and produce a mock recommendation. Free-form prose blurs those into one paragraph of compliments.
- **Two different models by default (same `claude-opus-4-7` now, but decoupled).** You can set `FEEDBACK_MODEL=claude-sonnet-4-6` to get critique from a different model than the one you interviewed with — sometimes useful for a second opinion.
- **No grading during the interview.** The persona prompts explicitly instruct "do not grade during the interview." If you ask them to evaluate you mid-session, they defer. This keeps the interview realistic.
- **Per-dimension rubric per persona.** The dimensions a coding interviewer scores you on are different from a behavioral interviewer's. Feedback is apples-to-apples within a persona, not forced into a single global rubric.

## Development

```bash
pip install -e ".[dev]"
pytest
black --check src tests
isort --check-only --profile black src tests
flake8 src tests --max-line-length=100 --ignore=E501,W503,E203
```

## Roadmap

- [x] **v0.2 — longitudinal tracking: `progress` subcommand shows per-dimension trends with sparklines**
- [ ] v0.3 — custom persona packs loaded from a YAML file (user-defined rubrics)
- [ ] v0.4 — replay mode: step through past sessions with alternative feedback models
- [ ] v0.5 — web UI (FastAPI + HTMX)

### Progress tracking (v0.2)

```
agent-interviewer progress
# Or just one persona:
agent-interviewer progress -t system-design
```

Reads every paired (transcript, feedback) in the sessions dir, groups by persona, and shows per-dimension sparklines + trend-since-prior-sessions. Scores from different personas are never averaged together (each persona's rubric is different by design).

## License

MIT. See [LICENSE](LICENSE).
