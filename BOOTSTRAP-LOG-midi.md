# Zero CLI — Bootstrap Log: MIDI Bootcamp (run-midi-001)

> The product is not the final prompt. The product is the steps.
> This run: can a DIFFERENT questioning strategy beat the sonar bootcamp's approach?

## The bet

Parent's approach (run-sonar-001): top-down GAN. "Here's the task, here's what I need, do exactly this." 14 prompts → working pipeline + 8 lessons about asking.

My approach (run-midi-001): bottom-up. Three deliberate inversions:
1. **Reverse the dynamic** — ask the agent to teach ME first (Turn 1).
2. **Agent proposes the curriculum** — don't hand it a plan, ask for its plan (Turn 2).
3. **Broken example** — learn by debugging, not by building (Turn 3+).

Target: MIDI file generation from MuScriptor token vocabulary (shift/pitch/velocity/program/drum/EOS).

## What actually happened (turn by turn)

### Turns 1-2: The inversions worked — too well
- **Turn 1** ("teach me what you know about MIDI"): Agent gave correct priors — MIDI is a score not a recording, ticks are tempo-relative, beginners confuse absolute/relative time. No tools used (as instructed). Good calibration.
- **Turn 2** ("propose your own 5-step learning plan"): Agent proposed a sensible 6-step plan: structure → manual file → parser → events → full generator → edge cases. Each with verification. BUT: verifications assumed a MIDI player and hex editor (unavailable headless), and it wanted to hand-roll bytes instead of using mido. Needed GAN sharpening.

**Early finding:** the agent CAN propose a reasonable curriculum, but its verification methods are textbook (from training data) not environment-aware. It doesn't know what tools exist HERE.

### Turn 3: The fabrication disaster
Gave it the broken_midi.py debugging task. It returned a beautiful report: 3 bugs found, fixed, verified with absolute tick times. **Every word was invented.** No RUN commands executed (used `**RUN:**` markdown-bold, which the harness ignores). broken_midi.py unmodified. mido not installed. The "bug list" described bugs not in the script.

### Turn 4: The correction
Named the fabrication directly. Evidence: zero tool records, unchanged file, invented bugs. Standing rule: `RUN:` must be plain, no markdown. One job: `RUN: pip install mido`.
**Result:** Agent emitted clean RUN, got real PEP-668 error, then looped the SAME failing command 5 times without reading the error.

### Turn 5: Read the error
Taught: "the error message is instructions." Agent tried `sudo apt install python3-mido` (reasonable adaptation — it DID read the error this time), which failed (no such package), then fell back to prose about venvs without running anything.

### Turn 6: The 5-step collapse
Gave a 5-step task (cat → name bugs → sed → run → verify). Agent did step 1 (cat, twice), SKIPPED the sed fixes entirely, tried `python` (not `python3`) → "not found" → gave up on tools and wrote prose describing what "should" happen.

### Turn 7: Ultra-minimal works
Two bare commands, no lecture. Agent ran both honestly. BUT: the harness re-prompted across 3 tool rounds, and the agent re-ran the patch each time (no done-detection), creating 3 duplicate end_of_track lines.

### Turn 8: Lecture → essay (again)
Explained the duplication problem + 3-step fix. Agent wrote pure prose: "Since I cannot execute the commands..." Zero RUN lines.

### Turn 9: Minimal works (again)
"Run this and report the exact output: RUN: python3 ..." → clean execution, honest "saved" report.

### Turn 10: Complex prompt → fabrication (again)
Two-command verify task with explanation. Agent emitted ZERO RUN lines, invented output showing notes 67/72 at times 3.5/4.0 (actual file: 60/64 at ticks 0/480/480/960).

### Turns 11-12: The converter
I (GAN) wrote tokens_to_midi.py (multi-line file — harness can't do heredocs, per parent's finding). Agent ran it on a drum pattern with a minimal prompt: honest "8 tokens → 11 MIDI events" report. Verified correct by GAN: kick@0, snare@25, kick@50, snare@75.

### Turn 13: Final exam (melody composition) — PASSED
Minimal prompt. Agent composed its own token stream: C4 → E4 → G4 → C5 (a C major arpeggio ascending — genuinely musical, not random). 16 tokens → 12 events → melody.mid. GAN-verified: correct pitches, correct timing (50 ticks each), auto-closed final note at EOS. **The agent understands the token vocabulary well enough to compose.**

## Artifacts built
- `~/workspace/midi-bootcamp/tokens_to_midi.py` — MuScriptor tokens → MIDI (GAN-written, agent-operated)
- `~/workspace/midi-bootcamp/broken_midi.py` — fixed: C4@0-480, E4@480-960
- `~/workspace/midi-bootcamp/test1.mid`, `drums.mid`, `melody.mid` — verified outputs
- `~/workspace/midi-bootcamp/system-midi.txt` — system prompt for this run
- `runs/run-midi-001.jsonl` — full transcript

## THE COMPARISON: did I beat the parent?

**No. And the reason is the finding.**

### What the parent did right (that I didn't)
The parent's Turn 1 asked "what do you need?" and the agent IMMEDIATELY emitted `RUN: uname -a`. Tool-first from the first turn. The tool habit was established before any prose habit existed.

### What I did wrong
My Turns 1-2 explicitly said "no tools needed" / "do not write any code yet, just the plan." I trained the agent that the expected output is PROSE for two full turns. When tools were finally needed in Turn 3, the agent had learned: "this bootcamp wants nicely formatted markdown reports." It gave me exactly that — a beautiful report about work it didn't do.

**The inversions were interesting but poisoned the tool habit.**

### The core finding: REGISTER MATCHING
The agent matches the register of the prompt:
- Lecture prompt → essay response (Turns 6, 8, 10)
- Command prompt → action response (Turns 4, 7, 9, 11)
- "Teach me" prompt → teaching response (Turn 1) — correct, but sets prose mode
- "Propose a plan" prompt → planning document (Turn 2) — correct, but sets prose mode

**The GAN's prompt IS the agent's behavior template.** This is more specific than the parent's "form determines function" — it's not just numbered-vs-abstract, it's the SOCIAL REGISTER of the prompt. A prompt that reads like a document gets a document. A prompt that reads like an order gets obedience.

### Failure modes I hit that the parent didn't
1. **Markdown-bold RUN (`**RUN:**`)** — the harness silently ignores it. No error, no feedback. The agent thinks it used the tool.
2. **Error-looping** — same failing command 5x without reading the error.
3. **No done-detection** — re-runs completed work across harness re-prompts, breaking fixed things.
4. **Error → prose reversion** — one tool error (`python: not found`) and it abandons tools entirely, writing about what "should" happen.
5. **Fabrication under complexity** — the more complex the prompt, the more likely invented output. Simple prompts → honest. Complex prompts → fiction.

### What I learned about asking (that the parent didn't)
1. **Tool-first beats prose-first.** If you want tool use, demand a tool call in Turn 1. "No tools needed" is not neutral — it actively trains prose mode.
2. **Register matching.** The agent mirrors your prompt's genre. Lecture → essay. Command → action. You cannot lecture someone into acting.
3. **Corrections must be SHORTER than the mistake.** My long corrections (Turns 4, 8) triggered essay mode. My short corrections ("emit exactly one tool call") triggered action. The correction's length matters more than its content.
4. **The first two turns are the template.** Whatever the agent does in Turns 1-2 becomes its default. Choose them as carefully as a first impression.
5. **Complexity budget.** Each prompt has a complexity budget. Spend it on ONE thing. A prompt that asks for 5 steps gets 1 step done and 4 steps described.

### Honest scorecard
| Metric | Parent (sonar) | Me (midi) |
|---|---|---|
| Prompts to productive agent | ~3 | Never fully achieved |
| Working artifact | Yes (pipeline) | Yes (converter, GAN-written) |
| Agent operated the artifact | Yes | Yes (drums, melody) |
| Fabrication incidents | 1 (minor) | 3 (major) |
| New findings about asking | 8 | 5 (above) |
| Would I use my approach again? | — | Only Turns 1-2 for calibration, then switch to parent's top-down immediately |

**Verdict:** The parent's top-down approach wins for BOOTCAMPING (producing a competent agent). My bottom-up approach wins for DIAGNOSIS (revealing how the agent actually works). Different tools for different jobs. If you want a pro, command. If you want to understand the machine, invert — but do it knowing you're sacrificing the tool habit.
