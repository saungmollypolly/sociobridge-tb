"""Held-out test of the rule-based checker (no API calls needed).

The rules were developed on the 8 pilot sentences (data/pilot_sentences.json). The data-collection
workbook has ~91 further sentences with a human Burmese reference. This script uses them in two ways:

1. Reference test (false positives): a human reference should be accepted by the checker.
   Every flag is either a false positive or a reference that really lacks a required marker; the
   script lists them so they can be inspected, it does NOT tune the rules.
2. Mutation test (detection): known errors are injected into each reference (wrong-gender particle,
   dropped particle, casual pronoun, generic address term, hedged alternatives, wrong self-reference,
   Thai script, commentary, dropped number). The checker should flag the expected rule.

Limits: injected errors are synthetic and simpler than real LLM errors, and only upward speech has
strict rules. This complements, and does not replace, a test on real model outputs with human labels.

Usage:  python src/eval_checker_heldout.py
Output: results/heldout_checker.json and results/heldout_checker_summary.txt
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sociobridge_checker import check, ADDRESS_TERMS, FINAL_MALE, FINAL_FEMALE, numbers  # noqa: E402
from workbook import load_workbook_sentences  # noqa: E402

PILOT_NOS = {1, 3, 4, 5, 6, 7, 8, 9}


def meta_for(s):
    role = s["listener"]["role"]
    return {"direction": s["social_hierarchy"]["direction"],
            "speaker_gender": s["speaker"]["gender"],
            "listener_role": role if role in ADDRESS_TERMS else None}


def rules_of(out, s):
    return {r for r, _ in check(out, meta_for(s), s["th"])}


# ----------------------------------------------------------------------------- mutations
def swap_particle(ref, s):
    g = s["speaker"]["gender"]
    if g not in ("Male", "Female"):
        return None
    good, bad = (FINAL_MALE, "ရှင့်") if g == "Male" else (FINAL_FEMALE, "ခင်ဗျာ")
    if not any(p in ref for p in good):
        return None
    for p in good:
        ref = ref.replace(p, bad)
    return ref


def drop_particle(ref, s):
    out = ref
    for p in FINAL_MALE + FINAL_FEMALE:
        out = out.replace(p, "")
    return out if out != ref else None


def add_casual(ref, s):
    return "ငါ " + ref


def generic_address(ref, s):
    role = s["listener"]["role"]
    if role not in ADDRESS_TERMS:
        return None
    out = ref
    for t in ADDRESS_TERMS[role]:
        out = re.sub(re.escape(t), "အထက်လူကြီး", out, flags=re.I)
    return out if out != ref else None


def hedge(ref, s):
    return "ဆရာမ/ဆရာ၊ " + ref


def wrong_self(ref, s):
    g = s["speaker"]["gender"]
    if g not in ("Male", "Female"):
        return None
    return ("ကျွန်မ " if g == "Male" else "ကျွန်တော် ") + ref


def thai_leak(ref, s):
    return ref + " ขอบคุณครับ"


def commentary(ref, s):
    return "**Translation:**\n" + ref


def drop_number(ref, s):
    if not numbers(s["th"]):
        return None
    out = re.sub(r"[0-9၀-၉]+|တစ်|နှစ်|သုံး|လေး|ငါး|ခြောက်|ခုနစ်|ရှစ်|ကိုး|ဆယ်", "", ref)
    return out if out != ref else None


MUTATIONS = [  # name, function, expected rule(s)
    ("wrong-gender final particle", swap_particle, {"R5"}),
    ("final particle removed", drop_particle, {"R4"}),
    ("casual pronoun added", add_casual, {"R8"}),
    ("generic address term", generic_address, {"R6"}),
    ("hedged alternatives", hedge, {"R3"}),
    ("wrong-gender self-reference", wrong_self, {"R7"}),
    ("Thai script leaked", thai_leak, {"R2"}),
    ("commentary / markdown", commentary, {"R1"}),
    ("number dropped", drop_number, {"R9"}),
]


def main():
    sents = [s for s in load_workbook_sentences() if s["ref_my"]]
    held = [s for s in sents if s["no"] not in PILOT_NOS]
    dev = [s for s in sents if s["no"] in PILOT_NOS]
    lines, result = [], {}

    def section(title, group):
        lines.append(f"\n== {title} (n={len(group)}) ==")
        by_dir = defaultdict(list)
        for s in group:
            fl = rules_of(s["ref_my"], s)
            by_dir[s["social_hierarchy"]["direction"]].append((s, fl))
        out = {}
        for d, items in by_dir.items():
            flagged = [(s, fl) for s, fl in items if fl]
            cnt = Counter(r for _, fl in flagged for r in fl)
            lines.append(f"{d}: references flagged {len(flagged)}/{len(items)}"
                         + (f"  by rule {dict(sorted(cnt.items()))}" if cnt else ""))
            out[d] = {"n": len(items), "flagged": len(flagged), "by_rule": dict(cnt),
                      "flagged_nos": [(s["no"], sorted(fl)) for s, fl in flagged]}
        return out

    result["reference_test_dev"] = section("Reference test, development sentences (pilot)", dev)
    result["reference_test_heldout"] = section("Reference test, held-out sentences", held)
    lines.append("\nFlagged held-out references (inspect: false positive or real gap in the reference):")
    for d, v in result["reference_test_heldout"].items():
        for no, fl in v["flagged_nos"]:
            s = next(x for x in held if x["no"] == no)
            lines.append(f"  #{no} [{d}] {fl}  speaker={s['speaker']['gender']} "
                         f"listener={s['listener']['role']}  ref={s['ref_my'][:60]}")

    up = [s for s in held if s["social_hierarchy"]["direction"] == "Upward"]

    # Diagnosis of the flags (descriptive only; the rules are NOT changed here)
    th_addr = ["หัวหน้า", "อาจารย์", "ครู", "ผู้จัดการ", "บอส", "ศาสตราจารย์", "ท่าน", "เจ้านาย"]
    flagged_by = {r: [s for s in up if r in rules_of(s["ref_my"], s)] for r in ("R3", "R4", "R6", "R9")}
    r6 = flagged_by["R6"]
    r6_noaddr = [s for s in r6 if not any(a in s["th"] for a in th_addr)]
    r4_informal = [s for s in flagged_by["R4"] if re.search(r"(ဗျ|ပါတယ်|ပါ|ဘူး)[။\s]*$", s["ref_my"])]
    r3_unk = [s for s in flagged_by["R3"] if s["listener"]["gender"] == "Unknown"]
    lines.append("\n== Diagnosis of held-out upward flags (descriptive; rules not modified) ==")
    lines.append(f"R6 ({len(r6)} flags): {len(r6_noaddr)} have NO address word in the Thai source "
                 f"(the rule requires an address term even when the speaker never addresses the listener); "
                 f"the other {len(r6) - len(r6_noaddr)} use a loanword/spelling variant (boss, Arjarn, 'manger').")
    lines.append(f"R4 ({len(flagged_by['R4'])} flags): {len(r4_informal)} end with an informal or neutral polite "
                 f"ending (e.g. ဗျ, ပါတယ်) that is not the formal ခင်ဗျာ / ရှင့်.")
    lines.append(f"R3 ({len(flagged_by['R3'])} flags): {len(r3_unk)} are references where the listener's gender is "
                 f"Unknown and the author wrote both forms (e.g. ဆရာ/ဆရာမ), i.e. hedging that is legitimate there.")
    lines.append(f"R9 ({len(flagged_by['R9'])} flag): a Thai time such as '11.00' yields the numbers 11 and 00, "
                 f"but the reference correctly writes 11.")
    result["diagnosis"] = {"R6_flags": len(r6), "R6_no_address_word_in_source": len(r6_noaddr),
                           "R4_flags": len(flagged_by["R4"]), "R4_informal_ending": len(r4_informal),
                           "R3_flags": len(flagged_by["R3"]), "R3_listener_gender_unknown": len(r3_unk),
                           "R9_flags": len(flagged_by["R9"])}

    lines.append("\n== Mutation test on held-out UPWARD references ==")
    mres = {}
    lines.append(f"{'injected error':34s} {'n':>3s} {'expected rule flagged':>22s} {'any flag':>9s}")
    for name, fn, expected in MUTATIONS:
        n = hit = anyf = 0
        misses = []
        for s in up:
            m = fn(s["ref_my"], s)
            if m is None:
                continue
            if rules_of(s["ref_my"], s):        # skip references the checker already rejects
                continue
            n += 1
            fl = rules_of(m, s)
            hit += bool(fl & expected)
            anyf += bool(fl)
            if not (fl & expected):
                misses.append((s["no"], sorted(fl)))
        mres[name] = {"n": n, "expected_rule_flagged": hit, "any_flag": anyf, "misses": misses[:10]}
        lines.append(f"{name:34s} {n:3d} {hit:>12d}/{n:<3d}{'':3s} {anyf:>5d}/{n}")
    result["mutation_test"] = mres
    tot = sum(v["n"] for v in mres.values())
    hit = sum(v["expected_rule_flagged"] for v in mres.values())
    lines.append(f"{'TOTAL':34s} {tot:3d} {hit:>12d}/{tot:<3d}")
    lines.append("(references already rejected by the checker are excluded from the mutation test)")

    (ROOT / "results").mkdir(exist_ok=True)
    json.dump(result, open(ROOT / "results" / "heldout_checker.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    text = "\n".join(lines) + "\n"
    (ROOT / "results" / "heldout_checker_summary.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
