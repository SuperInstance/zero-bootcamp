# zero-cli — grow an agent, document the steps

`zero-cli.py` is the simplest possible agent harness: a command line you
talk to. It sends your words to a language model and prints the reply.
It starts with **nothing** — no memory, no tools, no awareness. Just the
loop.

Then you grow it. You ask what it needs. It tells you. You add one tiny
capability at a time — a sense for hardware, a sense for time — and you
write down **every step**: what you said, what it said, *why* you said
it, what worked, what didn't.

**The product is not the final prompt. The product is the steps.**
The steps are hardware-agnostic and model-agnostic. Someone on different
hardware with a different model follows your log and grows a different —
but valid — agent. Do it enough times and the structure becomes obvious:
that's the incubation system.

## Quick start

```bash
# Local model (any machine with Ollama):
./zero-cli.py --backend ollama --model llama3.2

# Workspace-connected subscriptions (this Muse environment):
./zero-cli.py --backend minimax
./zero-cli.py --backend zai
./zero-cli.py --backend kimi        # 401 as of 2026-10-10, see Known issues
./zero-cli.py --backend anthropic   # 400 as of 2026-10-10, see Known issues

# Any OpenAI-compatible API (DeepSeek, etc.):
ZERO_API_BASE=https://api.deepseek.com ZERO_API_KEY=... ZERO_MODEL=deepseek-chat \
  ./zero-cli.py --backend openai

# One-shot (for scripted bootstrap steps):
./zero-cli.py --backend minimax --allow-run --system-file system-step5.txt \
  --run-id run-001 --once "What time is it?" --log runs/run-001.jsonl
```

Every turn appends to the JSONL log: timestamp, `run_id`, system prompt,
user input, model reply, backend, model, latency, token usage, estimated
cost. Nothing is hidden; the log *is* the experiment record.

## The RUN protocol (the first sense)

With `--allow-run`, the model may emit lines starting with `RUN:`
followed by a shell command. The harness executes them (all of them, up
to `--max-run-rounds` rounds), feeds the outputs back, and the model
synthesizes an answer. A denylist blocks obviously destructive commands.

This is deliberately the *first and only* tool for a long while. One
general sense (run a command, read the world) beats ten special-case
tools. The bootstrap log shows it generalizing from hardware questions
to time questions with zero new instruction.

## Running with different models

Same script, same steps, different `--backend` / `--model`:

```bash
./zero-cli.py --backend minimax --run-id run-minimax-001 --log runs/run-minimax-001.jsonl
./zero-cli.py --backend zai      --run-id run-zai-001      --log runs/run-zai-001.jsonl
./zero-cli.py --backend ollama --model llama3.2 --run-id run-ollama-001 --log runs/run-ollama-001.jsonl
```

Then follow the same five steps in [BOOTSTRAP-LOG.md](sandbox://workspace/zero-cli-bootstrap/BOOTSTRAP-LOG.md)
(Step 1: hello, Step 2: hardware ignorance, Step 3: add the RUN sense,
Step 4: transfer test on time, Step 5: name the senses) and write a new
log section per model with its own Incubation Run header:

```markdown
## Incubation Run
**Model:** [which LLM]
**Cost:** [estimated $, from zero-cost.py]
**Hardware:** [what machine]
**Date:** [when]
```

## Comparing bootstrap logs across models

Run the same steps, then diff the *behaviors*, not just the answers:

- **Identity:** when asked "what are you," does the model hold the
  "Zero" identity or leak its provider's name? (MiniMax leaked.)
- **Tool generalization:** taught one example command, how many does it
  propose? Does the sense transfer to new domains unprompted?
- **Gather vs. answer:** after tool output arrives, does it synthesize
  or keep gathering? (MiniMax needed explicit "answer now" framing.)
- **What does it ask for?** The most interesting inversion: let the
  *model* say what it needs next, and record what each model reaches
  for first. Kimi's list will differ from Claude's. Those differences
  are the finding.

Keep per-model logs in `runs/` (one JSONL + one log section each).
The comparison *is* the research.

## Cost tracking

```bash
./zero-cost.py runs/run-minimax-001.jsonl
# run_id: run-minimax-001
#   turns: 8  tool calls: 3
#   tokens in/out: 1234 / 567
#   est cost USD: $0.000000
#   backends: minimax
#   pricing: subscription
```

Cost model, set in `PRICING` inside `zero-cli.py`:

- **Subscription backends** (`minimax`, `kimi`, `zai`, `anthropic`):
  marginal cost per turn ≈ **$0.00**. The subscription is already paid;
  the log records that so comparisons stay honest.
- **Local** (`ollama`): $0.00 — your hardware, your electricity.
- **Per-token** (`openai` backend, e.g. DeepSeek): estimated $/1M
  in/out, overridable per run with `--price-in` / `--price-out`.
  Casey's rule of thumb: DeepSeek Flash (~$0.50-scale runs) — "sure,
  let's try it"; DeepSeek Pro (~$50-scale) — "maybe, if it's worth it."

The dollar figures are estimates; **the token counts are the durable
truth**. Reprice any old log with better numbers later — that's why both
are recorded.

## From bootstrap log to incubation system

One run is an anecdote. Five runs on five models is a pattern. The
pattern — same steps, same headers, same cost format, comparable logs —
*is* the incubation system: a reliable, repeatable way to grow an agent
from nothing on any hardware with any model.

The template for a new run:

1. Copy the Incubation Run header; fill in model, hardware, date.
2. Walk Steps 1–5 (or your evolved version — the steps themselves are
   allowed to improve, and the improvement gets logged).
3. Record cost with `zero-cost.py`.
4. Write down what this model did differently. That's the contribution.

## Files

| File | What it is |
|---|---|
| `zero-cli.py` | The harness (v2.0.0). The loop + RUN protocol + backends + cost tracking. |
| `zero-cost.py` | Per-run cost/token summary from a JSONL log. |
| `BOOTSTRAP-LOG.md` | The documented steps. The actual product. |
| `system-step3.txt` | System prompt that first declares the RUN tool. |
| `system-step5.txt` | System prompt naming HARDWARE SENSE and TIME SENSE. |
| `bootstrap-turns.jsonl` | Raw transcript of the first incubation run (pre-v2.0 schema). |
| `runs/` | Per-model run logs go here (create it when you start run 2). |

## Known issues

- `--backend kimi`: 401 Unauthorized as of 2026-10-10. The skill's own
  `bin/chat.py` fails identically, so it's the `custom.moonshot`
  connector, not this code. Needs a credential reconnect.
- `--backend anthropic`: 400 Bad Request as of 2026-10-10, also
  reproduced via the skill's own tool. Likely model ID or credential
  scope; needs investigation.
- The v1.x JSONL schema has no `run_id`/`usage` fields; `zero-cost.py`
  handles those logs gracefully (counts `[tool]`-prefixed records).

## Philosophy, briefly

- It's not the final prompt, it's the steps.
- A sense beats a fact. (Don't tell it the time; give it `date`.)
- Senses compose; trivia doesn't.
- Document the wrong predictions too. The log keeps the GAN honest.
- If the model is more capable than the harness, fix the harness.
