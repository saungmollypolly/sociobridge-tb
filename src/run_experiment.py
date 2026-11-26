"""Run the context-injection experiment (Observe -> Act).

Every sentence x condition pair is sent as a fresh, stateless API call:
no chat history, no session, nothing shared between calls. Results are
appended to a JSONL file so an interrupted run can be resumed.

Usage:
    python src/run_experiment.py --model gemini-3.6-flash --dry-run
    python src/run_experiment.py --model gemini-3.6-flash
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from prompts import CONDITIONS, CONDITION_LABELS, build_prompt

ROOT = Path(__file__).resolve().parent.parent


def load_sentences(path):
    data = json.load(open(path, encoding="utf-8"))["sentences"]
    for s in data:
        if "TODO" in json.dumps(s, ensure_ascii=False):
            print(f"WARNING: sentence {s['no']} still has TODO metadata values", file=sys.stderr)
    return data


def parse_translation(text):
    """Extract <translation> from the XML answer; fall back to raw text."""
    m = re.search(r"<translation>(.*?)</translation>", text, re.S)
    return (m.group(1) if m else text).strip()


def call_gemini(client, model, prompt, max_tokens):
    from google.genai import types
    config = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        # Translation needs no hidden reasoning; disabling it keeps cost predictable.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    resp = client.models.generate_content(model=model, contents=prompt, config=config)
    return resp.text or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.6-flash", help="model id as accepted by the Gemini API")
    ap.add_argument("--sentences", default=str(ROOT / "data" / "pilot_sentences.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "raw_outputs.jsonl"))
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between calls (free-tier rate limit)")
    ap.add_argument("--dry-run", action="store_true", help="print prompts only, no API calls")
    args = ap.parse_args()

    sentences = load_sentences(args.sentences)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = set()
    if out_path.exists():
        for line in open(out_path, encoding="utf-8"):
            r = json.loads(line)
            done.add((r["no"], r["model"], r["condition"]))

    client = None
    if not args.dry_run:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    for s in sentences:
        for cond in CONDITIONS:
            key = (s["no"], args.model, cond)
            if key in done:
                continue
            prompt = build_prompt(s, cond)
            if args.dry_run:
                print(f"===== sentence {s['no']} | {CONDITION_LABELS[cond]} =====\n{prompt}\n")
                continue
            raw = call_gemini(client, args.model, prompt, args.max_tokens)   # fresh call, no history
            rec = {"no": s["no"], "model": args.model, "condition": cond,
                   "cond": CONDITION_LABELS[cond], "th": s["th"], "ref": s["ref_my"],
                   "prompt": prompt, "raw": raw,
                   "out": raw if cond == "zero_shot" else parse_translation(raw)}
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"done: sentence {s['no']} | {CONDITION_LABELS[cond]}")
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
