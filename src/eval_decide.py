"""Evaluate the Decide stage and the repair step on the 8 pilot sentences (rule checker only).

Conditions (same model, same sentences, one fresh stateless call each):
  A  Full Context            the paper's existing outputs (data/pilot_outputs.json), already human-labelled
  B  Full Context + Decide   one call: the model commits to a politeness level, then translates
  C  B + one-shot repair     B, plus one targeted repair when the checker flags the output
                             (kept only if it has strictly fewer violations)
  A2 Full Context (re-run)   optional (--rerun): the paper prompt again, to measure run-to-run variation

Strict mode: only the requested model is used (no fallback), so results are never mixed across models.
The script is resumable: finished items are skipped (results/decide_eval.jsonl).

This script reports RULE-CHECKER results only. For MQM it writes results/decide_eval_for_annotation.csv,
which a human annotator fills in (a model must not score its own output).

Usage:
    python src/eval_decide.py --model gemini-3.6-flash
    python src/eval_decide.py --model gemini-3.6-flash --rerun
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline as pl  # noqa: E402
from prompts import context_prompt, build_prompt, OUTPUT_FORMAT  # noqa: E402
from run_experiment import parse_translation  # noqa: E402

OUT = ROOT / "results" / "decide_eval.jsonl"
ANNOT = ROOT / "results" / "decide_eval_for_annotation.csv"
SUMMARY = ROOT / "results" / "decide_eval_summary.txt"


def decide_prompt(s):
    """Paper Full Context prompt, with the output format asking for a committed level first."""
    cands = pl.candidate_levels(s)
    fmt = (f"First compare the politeness levels {', '.join(cands)} and commit to exactly one with a "
           "one-sentence reason, then translate accordingly. Answer ONLY in this XML format, with no other "
           'text: <result><decision level="...">reason</decision><translation>...</translation></result>')
    return context_prompt(s).replace(OUTPUT_FORMAT, fmt), cands


def load_done():
    done = {}
    if OUT.exists():
        for line in open(OUT, encoding="utf-8"):
            r = json.loads(line)
            done[(r["no"], r["cond"])] = r
    return done


def save(rec):
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.6-flash")
    ap.add_argument("--rerun", action="store_true", help="also re-run plain Full Context (8 more calls)")
    ap.add_argument("--sleep", type=float, default=1.5)
    args = ap.parse_args()

    pl.STRICT = True
    client = pl.get_client()
    if client is None:
        sys.exit("No API key (GEMINI_API_KEY in .env)")
    sents = json.load(open(ROOT / "data" / "pilot_sentences.json", encoding="utf-8"))["sentences"]
    done = load_done()
    calls = 0

    for s in sents:
        try:
            # ---- B: Full Context + Decide (single call)
            if (s["no"], "B") not in done:
                prompt, cands = decide_prompt(s)
                raw = pl._call(client, args.model, prompt)
                calls += 1
                import re
                m = re.search(r'<decision level="([^"]*)">(.*?)</decision>', raw, re.S)
                out = parse_translation(raw)
                v = pl.run_check(out, s)
                rec = {"no": s["no"], "cond": "B", "model": args.model,
                       "level": m.group(1) if m else None, "reason": m.group(2).strip() if m else None,
                       "out": out, "violations": [r for r, _ in v], "raw": raw}
                save(rec); done[(s["no"], "B")] = rec
                print(f"#{s['no']} B  level={rec['level']} violations={rec['violations']}", flush=True)
                time.sleep(args.sleep)
            # ---- C: repair when B is flagged
            b = done[(s["no"], "B")]
            if (s["no"], "C") not in done:
                if b["violations"]:
                    viol = pl.run_check(b["out"], s)
                    dec = {"level": b["level"] or "Formal", "reason": b["reason"] or ""}
                    fixed, _ = pl.repair(client, args.model, s, dec, b["out"], viol)
                    calls += 1
                    fv = pl.run_check(fixed, s)
                    use = len(fv) < len(viol)
                    rec = {"no": s["no"], "cond": "C", "model": args.model, "repaired": True,
                           "accepted": use, "out": fixed if use else b["out"],
                           "violations": [r for r, _ in (fv if use else viol)],
                           "repair_out": fixed, "repair_violations": [r for r, _ in fv]}
                    time.sleep(args.sleep)
                else:
                    rec = {"no": s["no"], "cond": "C", "model": args.model, "repaired": False,
                           "accepted": False, "out": b["out"], "violations": []}
                save(rec); done[(s["no"], "C")] = rec
                print(f"#{s['no']} C  repaired={rec['repaired']} accepted={rec['accepted']} "
                      f"violations={rec['violations']}", flush=True)
            # ---- A2: optional re-run of the plain paper prompt
            if args.rerun and (s["no"], "A2") not in done:
                raw = pl._call(client, args.model, build_prompt(s, "full_context"))
                calls += 1
                out = parse_translation(raw)
                rec = {"no": s["no"], "cond": "A2", "model": args.model, "out": out,
                       "violations": [r for r, _ in pl.run_check(out, s)]}
                save(rec); done[(s["no"], "A2")] = rec
                print(f"#{s['no']} A2 violations={rec['violations']}", flush=True)
                time.sleep(args.sleep)
        except Exception as e:
            print(f"STOPPED at sentence {s['no']}: {str(e)[:160]}", flush=True)
            print("Progress is saved; re-run the same command later to resume.")
            break

    report(sents, done)


def report(sents, done):
    po = json.load(open(ROOT / "data" / "pilot_outputs.json", encoding="utf-8"))
    meta = json.load(open(ROOT / "data" / "checker_metadata.json", encoding="utf-8"))
    from sociobridge_checker import check
    rows = {"A": {}, "B": {}, "C": {}, "A2": {}}
    for r in po:
        if r["cond"] == "Full Context":
            rows["A"][int(r["no"])] = {"out": r["out"], "violations": [x for x, _ in check(r["out"], meta[str(r["no"])], r["th"])],
                                        "label": r.get("acc"), "mqm": r.get("mqm")}
    for (no, c), r in done.items():
        rows[c][no] = r
    names = {"A": "Full Context (paper, human-labelled)", "B": "Full Context + Decide",
             "C": "Decide + repair", "A2": "Full Context re-run"}
    lines = ["Rule-checker results on the 8 pilot sentences (no MQM; see the annotation sheet)", ""]
    for c in ("A", "B", "C", "A2"):
        d = rows[c]
        if not d:
            continue
        n = len(d); ok = sum(1 for r in d.values() if not r["violations"])
        rules = {}
        for r in d.values():
            for x in r["violations"]:
                rules[x] = rules.get(x, 0) + 1
        lines.append(f"{names[c]:40s} pass {ok}/{n}   violations {dict(sorted(rules.items())) or '-'}")
    if rows["B"]:
        lv = {}
        for r in rows["B"].values():
            lv[r.get("level")] = lv.get(r.get("level"), 0) + 1
        lines.append(f"\nCommitted levels in B: {lv}")
    if rows["C"]:
        rep = [r for r in rows["C"].values() if r["repaired"]]
        lines.append(f"Repair attempted on {len(rep)}; accepted {sum(r['accepted'] for r in rep)}")
    text = "\n".join(lines) + "\n"
    SUMMARY.write_text(text, encoding="utf-8")
    print("\n" + text)

    with open(ANNOT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["No", "Condition", "Thai", "Human reference", "Output", "Checker violations",
                    "Human label (Accurate / Partially accurate / Not accurate)", "MQM errors", "MQM TQ"])
        refs = {s["no"]: (s["th"], s["ref_my"]) for s in sents}
        for c in ("A", "B", "C", "A2"):
            for no, r in sorted(rows[c].items()):
                w.writerow([no, names[c], refs[no][0], refs[no][1], r["out"], " ".join(r["violations"]),
                            r.get("label", "") if c == "A" else "", "", r.get("mqm", "") if c == "A" else ""])
    print(f"Annotation sheet: {ANNOT}")


if __name__ == "__main__":
    main()
