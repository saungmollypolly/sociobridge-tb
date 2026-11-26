"""SocioBridge-TB rule-based politeness checker (Check stage).

Offline, deterministic checker that verifies a Burmese translation against the
politeness requirements compiled in the Socio-Pragmatic Mapping Library for the
sentence's social context. It needs no API calls, so it can be run on already
generated outputs.

Usage:
    python src/sociobridge_checker.py data/pilot_outputs.json data/checker_metadata.json results/

Outputs (in out_dir):
    checker_results.json / .csv  - violations for every translation
    checker_summary.txt          - agreement with human labels + checker-guided selection
"""
import csv
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Socio-Pragmatic Mapping Library (compiled knowledge, subset used here)
# key: (direction, speaker_gender) -> required / forbidden Burmese markers
# ---------------------------------------------------------------------------
FINAL_MALE = ["ခင်ဗျာ", "ခင်ဗျ"]
FINAL_FEMALE = ["ရှင့်", "ရှင်"]
CASUAL_PRONOUNS = ["ငါ", "နင်"]

MAPPING_LIBRARY = {
    ("Upward", "Male"): {
        "final_particle": FINAL_MALE,
        "forbidden_particle": FINAL_FEMALE,
        "self_reference_allowed": ["ကျွန်တော်", "ကျွန်တော့်"],
        "self_reference_forbidden": ["ကျွန်မ", "သမီး", "ညီမ", "မမ"],
        "forbidden_pronouns": CASUAL_PRONOUNS,
    },
    ("Upward", "Female"): {
        "final_particle": FINAL_FEMALE,
        "forbidden_particle": FINAL_MALE,
        "self_reference_allowed": ["ကျွန်မ", "သမီး"],
        "self_reference_forbidden": ["ကျွန်တော်", "ညီမ", "မမ"],
        "forbidden_pronouns": CASUAL_PRONOUNS,
    },
    # Equal / downward speech: no polite particle is required and casual pronouns
    # are acceptable. Only gender-inconsistent self-reference is still forbidden.
    ("Equal", "Male"): {
        "final_particle": [], "forbidden_particle": [],
        "self_reference_allowed": [], "self_reference_forbidden": ["ကျွန်မ"],
        "forbidden_pronouns": [],
    },
    ("Equal", "Female"): {
        "final_particle": [], "forbidden_particle": [],
        "self_reference_allowed": [], "self_reference_forbidden": ["ကျွန်တော်"],
        "forbidden_pronouns": [],
    },
    ("Downward", "Male"): {
        "final_particle": [], "forbidden_particle": [],
        "self_reference_allowed": [], "self_reference_forbidden": ["ကျွန်မ"],
        "forbidden_pronouns": [],
    },
    ("Downward", "Female"): {
        "final_particle": [], "forbidden_particle": [],
        "self_reference_allowed": [], "self_reference_forbidden": ["ကျွန်တော်"],
        "forbidden_pronouns": [],
    },
}

# Required address term for the listener role given in the metadata
ADDRESS_TERMS = {
    "Manager": ["မန်နေဂျာ", "manager"],
    "Professor": ["ဆရာ", "ပါမောက္ခ", "professor"],
    "Teacher": ["ဆရာ", "ဆရာမ", "teacher"],
}

def gender_unknown_rules(direction):
    """Fallback when the speaker gender is unknown: accept either gender's
    markers, and forbid nothing gender-specific."""
    upward = direction == "Upward"
    return {"final_particle": FINAL_MALE + FINAL_FEMALE if upward else [],
            "forbidden_particle": [], "self_reference_allowed": [],
            "self_reference_forbidden": [],
            "forbidden_pronouns": CASUAL_PRONOUNS if upward else []}


THAI_DIGITS ="๐๑๒๓๔๕๖๗๘๙"
MY_DIGITS = "၀၁၂၃၄၅၆၇၈၉"


# Burmese number words (1-10), so "နှစ်ရက်" counts as "2 days"
MY_NUMBER_WORDS = {"တစ်": "1", "နှစ်": "2", "သုံး": "3", "လေး": "4", "ငါး": "5",
                   "ခြောက်": "6", "ခုနစ်": "7", "ရှစ်": "8", "ကိုး": "9", "ဆယ်": "10"}


def numbers(text):
    """Return the set of numbers in a string, normalising Thai/Burmese digits
    and Burmese number words."""
    t = text.translate(str.maketrans(THAI_DIGITS + MY_DIGITS, "0123456789" * 2))
    found = set(re.findall(r"\d+", t))
    found |= {d for w, d in MY_NUMBER_WORDS.items() if w in text}
    return found


def check(output, meta, source):
    """Return a list of (rule_id, message) violations for one translation."""
    v = []
    key = (meta["direction"], meta["speaker_gender"])
    rules = MAPPING_LIBRARY.get(key) or gender_unknown_rules(meta["direction"])

    # R1 Output format: a single translated sentence, no commentary/markdown
    if "\n" in output.strip() or "**" in output or re.search(r"^\s*[*>#-]", output, re.M):
        v.append(("R1", "Output is not a single sentence (commentary/markdown present)"))

    # R2 Script leakage: Thai characters inside the Burmese output
    if re.search(r"[฀-๿]", output):
        v.append(("R2", "Thai script found in Burmese output"))

    # R3 Unresolved alternatives (hedged address/gender options)
    if re.search(r"[က-႟]\s*/\s*[က-႟]", output) or re.search(r"\([က-႟/ ]+\)", output):
        v.append(("R3", "Unresolved alternative forms ('/' or parentheses)"))

    # R4 Required polite final particle for this hierarchy/gender
    if rules["final_particle"] and not any(p in output for p in rules["final_particle"]):
        v.append(("R4", "Missing required polite final particle"))

    # R5 Wrong-gender final particle
    if any(p in output for p in rules["forbidden_particle"]):
        v.append(("R5", "Final particle of the wrong speaker gender"))

    # R6 Address term must match the listener role in the metadata
    terms = ADDRESS_TERMS.get(meta["listener_role"] or "", [])
    if terms and not any(t.lower() in output.lower() for t in terms):
        v.append(("R6", f"Address term for '{meta['listener_role']}' not used"))

    # R7 Self-reference must fit speaker gender and hierarchy
    if any(s in output for s in rules["self_reference_forbidden"]):
        v.append(("R7", "Self-reference does not fit speaker gender/hierarchy"))

    # R8 Casual pronouns forbidden in upward speech
    if any(p in output for p in rules["forbidden_pronouns"]):
        v.append(("R8", "Casual pronoun in upward speech"))

    # R9 Numbers in the source must be preserved
    if numbers(source) - numbers(output):
        v.append(("R9", "Number in source not preserved"))

    return v


SELECT_ORDER = ["Full Context", "Ablation: No Social Hierarchy",
                "Ablation: No Social Distance", "Ablation: No Communicative Intent"]


def evaluate(results):
    """Compare checker flags with human labels (anything not 'Accurate' = error)."""
    tp = sum(r["flagged"] and r["acc"] != "Accurate" for r in results)
    fp = sum(r["flagged"] and r["acc"] == "Accurate" for r in results)
    fn = sum((not r["flagged"]) and r["acc"] != "Accurate" for r in results)
    tn = sum((not r["flagged"]) and r["acc"] == "Accurate" for r in results)
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=p, recall=rc, f1=f1)


def select(results):
    """Generate -> evaluate -> select: keep Full Context unless flagged,
    otherwise take the first unflagged context-bearing candidate."""
    picks = []
    for no in sorted({r["no"] for r in results}):
        cand = {r["cond"]: r for r in results if r["no"] == no}
        pick = next((cand[c] for c in SELECT_ORDER if c in cand and not cand[c]["flagged"]),
                    cand.get("Full Context"))
        picks.append(pick)
    return picks


def main(rows_path, meta_path, out_dir):
    rows = json.load(open(rows_path, encoding="utf-8"))
    meta = json.load(open(meta_path, encoding="utf-8"))
    out = []
    for r in rows:
        viol = check(r["out"], meta[str(r["no"])], r["th"])
        out.append({**r, "violations": viol, "flagged": bool(viol)})
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(out_dir / "checker_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(out_dir / "checker_results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["No", "Condition", "Human label", "MQM TQ", "Flagged", "Violated rules", "Messages", "Output"])
        for r in out:
            w.writerow([r["no"], r["cond"], r.get("acc", ""), r.get("mqm", ""), r["flagged"],
                        " ".join(v[0] for v in r["violations"]),
                        "; ".join(v[1] for v in r["violations"]), r["out"]])

    lines = []
    if all("acc" in r for r in out):
        e = evaluate(out)
        lines.append("Checker vs. human labels: TP={tp} FP={fp} FN={fn} TN={tn}".format(**e))
        lines.append(f"Precision={e['precision']:.2f} Recall={e['recall']:.2f} F1={e['f1']:.2f}")
    for cond in dict.fromkeys(r["cond"] for r in out):
        rs = [r for r in out if r["cond"] == cond]
        lines.append(f"{cond}: flagged {sum(r['flagged'] for r in rs)}/{len(rs)}, "
                     f"violations {sum(len(r['violations']) for r in rs)}")
    picks = select(out)
    if all("acc" in r for r in picks):
        acc = sum(r["acc"] == "Accurate" for r in picks)
        lines.append(f"Checker-guided selection: {acc}/{len(picks)} accurate")
        if all("mqm" in r for r in picks):
            lines.append(f"Checker-guided selection: mean MQM TQ = {sum(r['mqm'] for r in picks)/len(picks):.1f}")
    lines += [f"  sentence {r['no']}: {r['cond']}" for r in picks]
    (out_dir / "checker_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return out


if __name__ == "__main__":
    main(*sys.argv[1:4])
