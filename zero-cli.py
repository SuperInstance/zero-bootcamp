#!/usr/bin/env python3
"""zero-cli.py — the simplest possible agent harness, now multi-model.

A command line you talk to. It sends your words to a language model and
prints the reply. That is all it does.

v1.0.0: no memory, no tools, no awareness. Just the loop.
v1.1.0: the RUN protocol (model may emit "RUN: <shell command>" lines;
        harness executes them and feeds output back). Gated by --allow-run.
v2.0.0: multi-model backends (ollama, openai-compatible, minimax, kimi,
        zai, anthropic), usage + cost tracking per turn, --run-id so a
        whole bootstrap run groups together, and multi-RUN chaining
        (the model may emit several RUN: lines; all execute per round).

Every turn is logged to JSONL: timestamp, run_id, system prompt, user
input, model reply, backend, model name, latency, token usage,
estimated cost.

Backends:
  ollama     http://localhost:11434 (default) — no auth, any machine
             with Ollama. Model via --model (default llama3.2).
  openai     Any OpenAI-compatible chat-completions endpoint.
             Env: ZERO_API_BASE, ZERO_API_KEY, ZERO_MODEL.
             (DeepSeek: ZERO_API_BASE=https://api.deepseek.com,
              ZERO_MODEL=deepseek-chat — pay-per-token, see PRICING.)
  minimax    Workspace-connected MiniMax credential (custom.minimax).
  kimi       Workspace-connected Moonshot/Kimi credential (custom.moonshot).
  zai        Workspace-connected ZAI credential (custom.zai).
  anthropic  Workspace-connected Anthropic credential (custom.anthropic).

The credential-backed backends only work where those credentials are
connected (this Muse environment). Anywhere else, use ollama or openai.

Usage:
  ./zero-cli.py [--backend ollama|openai|minimax|kimi|zai|anthropic]
                [--model NAME] [--run-id ID]
                [--system-prompt TEXT | --system-file PATH]
                [--log PATH] [--once "single prompt"]
                [--allow-run] [--max-run-rounds N]
"""
import sys
import os
import re
import json
import time
import argparse
import subprocess
import urllib.request
from datetime import datetime, timezone

VERSION = "2.0.0"

RUN_DENYLIST = ("rm -rf /", "mkfs", ":(){", "dd if=", "> /dev/sd")

DEFAULT_SYSTEM = (
    "You are Zero, a newly created agent. "
    "You have no memory of past conversations, no tools, and no knowledge "
    "of the machine or environment you run on. "
    "Answer honestly about what you do and do not know."
)

# ---------------------------------------------------------------- pricing
# Estimates only, as of 2026-10. Subscription backends have ~$0 marginal
# cost per turn (the subscription is already paid); per-token backends use
# the estimates below unless --price-in/--price-out override them.
# When in doubt the JSONL's raw token counts are the durable truth —
# reprice later with better numbers.
PRICING = {
    "ollama":    {"type": "local", "note": "runs on your own hardware"},
    "minimax":   {"type": "subscription", "plan": "MiniMax subscription"},
    "kimi":      {"type": "subscription", "plan": "Kimi/Moonshot subscription"},
    "zai":       {"type": "subscription", "plan": "ZAI subscription"},
    "anthropic": {"type": "subscription", "plan": "Claude Pro subscription"},
    "openai":    {"type": "per_token", "per_1m_in": 0.27, "per_1m_out": 1.10,
                  "note": "estimate; e.g. DeepSeek chat pricing — override with flags"},
}


def estimate_cost(backend, usage, price_in=None, price_out=None):
    """Return (est_cost_usd, pricing_note)."""
    spec = PRICING.get(backend, {"type": "unknown"})
    if spec["type"] != "per_token" or not usage:
        return 0.0, spec.get("type", "unknown")
    pin = price_in if price_in is not None else spec["per_1m_in"]
    pout = price_out if price_out is not None else spec["per_1m_out"]
    cost = (usage.get("prompt_tokens", 0) / 1e6) * pin \
         + (usage.get("completion_tokens", 0) / 1e6) * pout
    return round(cost, 6), f"per_token est @{pin}/{pout} per 1M in/out"


# ---------------------------------------------------------------- backends
# Each chat function returns (text, usage_dict). usage_dict uses
# OpenAI-style keys: {"prompt_tokens": n, "completion_tokens": n}.

def _post_json(url, body, headers, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode())


def ollama_chat(base, model, system, user, timeout=120, **kw):
    data = _post_json(base.rstrip("/") + "/api/chat", {
        "model": model, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }, {"Content-Type": "application/json"}, timeout)
    usage = {"prompt_tokens": data.get("prompt_eval_count", 0),
             "completion_tokens": data.get("eval_count", 0)}
    return data["message"]["content"], usage


def openai_compat_chat(base, api_key, model, system, user, timeout=120,
                       max_tokens=4000, temperature=0.7, **kw):
    data = _post_json(base.rstrip("/") + "/chat/completions", {
        "model": model, "max_tokens": max_tokens, "temperature": temperature,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }, {"Content-Type": "application/json",
        "Authorization": "Bearer " + api_key}, timeout)
    u = data.get("usage", {})
    usage = {"prompt_tokens": u.get("prompt_tokens", 0),
             "completion_tokens": u.get("completion_tokens", 0)}
    return data["choices"][0]["message"]["content"], usage


def _cred_chat(connector, host, url, model, system, user, timeout=120,
               max_tokens=4000, temperature=0.7):
    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    from dynamic_credentials import add_surrogate_to_request, read_json_response
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "temperature": temperature,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    add_surrogate_to_request(req, connector, allowed_hosts=[host])
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = read_json_response(resp)
    u = data.get("usage", {})
    usage = {"prompt_tokens": u.get("prompt_tokens", 0),
             "completion_tokens": u.get("completion_tokens", 0)}
    return data["choices"][0]["message"]["content"], usage


def anthropic_chat(model, system, user, timeout=120, max_tokens=4000, **kw):
    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    from dynamic_credentials import add_surrogate_to_request, read_json_response
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages",
                                 data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("anthropic-version", "2023-06-01")
    add_surrogate_to_request(req, "custom.anthropic",
                             allowed_hosts=["api.anthropic.com"])
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = read_json_response(resp)
    text = "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text")
    u = data.get("usage", {})
    usage = {"prompt_tokens": u.get("input_tokens", 0),
             "completion_tokens": u.get("output_tokens", 0)}
    return text, usage


CRED_BACKENDS = {
    # backend: (connector, host, url, default_model)
    "minimax": ("custom.minimax", "api.minimax.io",
                "https://api.minimax.io/v1/chat/completions", "MiniMax-Text-01"),
    "kimi":    ("custom.moonshot", "api.moonshot.ai",
                "https://api.moonshot.ai/v1/chat/completions", "kimi-k2.5"),
    # audited 2026-10-09: glm-4.5 returns 429 for this key; glm-4.5-flash works
    "zai":     ("custom.zai", "api.z.ai",
                "https://api.z.ai/api/paas/v4/chat/completions", "glm-4.5-flash"),
}


# ---------------------------------------------------------------- RUN tool
def run_tool(command, timeout=15):
    """Execute a model-requested shell command. Returns (ok, output)."""
    for bad in RUN_DENYLIST:
        if bad in command:
            return False, f"refused by harness seatbelt (matched denylist: {bad!r})"
    try:
        proc = subprocess.run(command, shell=True, capture_output=True,
                              text=True, timeout=timeout)
        out = (proc.stdout or "") + (proc.stderr or "")
        return True, out.strip()[:4000] or "(no output)"
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except Exception as e:
        return False, f"execution failed: {e}"


RUN_RE = re.compile(r"^RUN:\s*(.+)$", re.MULTILINE)


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="zero-cli: the simplest agent harness")
    p.add_argument("--backend", default="ollama",
                   choices=["ollama", "openai", "minimax", "kimi", "zai", "anthropic"])
    p.add_argument("--model", default=None, help="Model name (backend default if omitted)")
    p.add_argument("--run-id", default=None,
                   help="Incubation run id; defaults to run-<UTC timestamp>")
    p.add_argument("--system-prompt", default=None)
    p.add_argument("--system-file", default=None)
    p.add_argument("--log", default="zero-cli-log.jsonl")
    p.add_argument("--once", default=None, help="Single prompt, then exit (for scripting)")
    p.add_argument("--ollama-base", default="http://localhost:11434")
    p.add_argument("--allow-run", action="store_true",
                   help="Enable the RUN: tool protocol (model may execute shell commands)")
    p.add_argument("--max-run-rounds", type=int, default=5,
                   help="Max RUN:/follow-up rounds per turn (default 5)")
    p.add_argument("--max-tokens", type=int, default=4000)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--price-in", type=float, default=None,
                   help="Override $/1M input tokens for cost estimate")
    p.add_argument("--price-out", type=float, default=None,
                   help="Override $/1M output tokens for cost estimate")
    args = p.parse_args()

    run_id = args.run_id or ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))

    if args.system_file:
        with open(args.system_file) as f:
            system = f.read()
    else:
        system = args.system_prompt or DEFAULT_SYSTEM

    kw = {"timeout": 120, "max_tokens": args.max_tokens, "temperature": args.temperature}
    if args.backend == "ollama":
        model = args.model or os.environ.get("ZERO_MODEL", "llama3.2")
        def ask(user):
            return ollama_chat(args.ollama_base, model, system, user, **kw)
    elif args.backend == "openai":
        base = os.environ.get("ZERO_API_BASE", "")
        key = os.environ.get("ZERO_API_KEY", "")
        model = args.model or os.environ.get("ZERO_MODEL", "")
        if not base or not key or not model:
            print("ERROR: openai backend needs ZERO_API_BASE, ZERO_API_KEY, ZERO_MODEL",
                  file=sys.stderr)
            sys.exit(2)
        def ask(user):
            return openai_compat_chat(base, key, model, system, user, **kw)
    elif args.backend == "anthropic":
        model = args.model or "claude-sonnet-4-5-20250929"
        def ask(user):
            return anthropic_chat(model, system, user, **kw)
    else:  # minimax | kimi | zai
        connector, host, url, default_model = CRED_BACKENDS[args.backend]
        model = args.model or default_model
        def ask(user, _c=connector, _h=host, _u=url):
            return _cred_chat(_c, _h, _u, model, system, user, **kw)

    def log(record):
        record.update({"ts": datetime.now(timezone.utc).isoformat(),
                       "cli_version": VERSION, "run_id": run_id,
                       "backend": args.backend, "model": model,
                       "system_prompt": system, "allow_run": args.allow_run})
        with open(args.log, "a") as f:
            f.write(json.dumps(record) + "\n")

    def priced(usage):
        cost, note = estimate_cost(args.backend, usage, args.price_in, args.price_out)
        return {"usage": usage, "est_cost_usd": cost, "pricing": note}

    def turn(user_text):
        t0 = time.time()
        try:
            reply, usage = ask(user_text)
            err = None
        except Exception as e:
            reply, usage, err = None, {}, str(e)
        rec = {"kind": "turn", "user": user_text, "assistant": reply, "error": err,
               "latency_s": round(time.time() - t0, 2)}
        rec.update(priced(usage))
        log(rec)
        if err or not args.allow_run:
            return reply, err
        # RUN protocol, multi-round: execute every RUN: line the model emits,
        # feed all outputs back, repeat until no RUN: lines or round cap.
        for rnd in range(args.max_run_rounds):
            cmds = [c.strip() for c in RUN_RE.findall(reply or "")]
            if not cmds:
                break
            results = []
            for cmd in cmds:
                ok, output = run_tool(cmd)
                results.append((cmd, ok, output))
                r2 = {"kind": "tool", "user": f"[tool] {cmd}", "assistant": None,
                      "tool_output": output, "tool_ok": ok, "error": None,
                      "latency_s": 0}
                r2.update(priced({}))
                log(r2)
            blob = "\n\n".join(f"$ {c}\n{o}" for c, _, o in results)
            follow = (f"You ran these commands:\n{blob}\n\n"
                      f"My original question was: {user_text}\n"
                      f"If the outputs above answer it, answer it directly now "
                      f"in plain language with NO further RUN: lines. "
                      f"Only emit another RUN: line if an output was empty, "
                      f"failed, or clearly insufficient — otherwise synthesize "
                      f"and finish.")
            t1 = time.time()
            try:
                reply, usage = ask(follow)
                err = None
            except Exception as e:
                reply, usage, err = None, {}, str(e)
            rec = {"kind": "turn", "user": f"[after tool round {rnd+1}] {user_text}",
                   "assistant": reply, "error": err,
                   "latency_s": round(time.time() - t1, 2)}
            rec.update(priced(usage))
            log(rec)
            if err:
                break
        return reply, err

    if args.once:
        reply, err = turn(args.once)
        if err:
            print(f"ERROR: {err}", file=sys.stderr)
            sys.exit(1)
        print(reply)
        return

    print(f"zero-cli v{VERSION} [{args.backend}/{model}] run_id={run_id}")
    print("type, enter, read. Ctrl-D to quit.")
    print(f"logging to {args.log}")
    try:
        while True:
            try:
                user_text = input("\nyou> ").strip()
            except EOFError:
                print()
                break
            if not user_text:
                continue
            reply, err = turn(user_text)
            if err:
                print(f"zero [error]> {err}")
            else:
                print(f"\nzero> {reply}")
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
