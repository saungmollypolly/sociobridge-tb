"""Score translations per condition: BLEU, chrF, chrF++ (corpus level, sacreBLEU)
plus MQM aggregates (mean sentence TQ, number of Accurate sentences).

MQM sentence score:  TQ = 100 - (sum_i n_i * w_i) / N * 100   (floored at 0)
where N is the word count of the human reference (space-separated words).
Pooled TQ per condition: 100 - (total penalty / total reference words) * 100, floored at 0.
Each record's "errors" field holds the annotated error counts per category; the script checks that
they reproduce the stored sentence score ("mqm") and stops if they do not.
The last row applies checker-guided selection (Full Context unless flagged, else the first
unflagged context-bearing candidate), as in src/sociobridge_checker.py.

Usage:
    python src/score.py data/pilot_outputs.json results/scores.csv
"""
import csv
import json
import statistics
import sys
from collections import OrderedDict

import sacrebleu
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Provisional weights (pending advisor confirmation)
MQM_WEIGHTS = {
    "Accuracy": 25,
    "Honorific Mismatch": 5,
    "Register Collapse": 5,
    "Socio-Pragmatic Error": 5,
    "Literal Metaphor Error": 5,
    "Literal Translation Bias": 5,
    "Style/Formality Error": 2,
    "Polite Particle Omission": 1,
}


def mqm_penalty(error_counts):
    """error_counts: {category: n}. Returns the weighted penalty sum."""
    return sum(MQM_WEIGHTS[c] * n for c, n in error_counts.items())


def mqm_tq(error_counts, ref_word_count):
    """Sentence-level MQM translation-quality score, floored at 0."""
    return max(0.0, 100 - mqm_penalty(error_counts) / ref_word_count * 100)


def ref_words(r):
    return len(r["ref"].split())


def pooled_tq(rs):
    pen = sum(mqm_penalty(r["errors"]) for r in rs)
    return max(0.0, 100 - pen / sum(ref_words(r) for r in rs) * 100)


def selected_rows(rows, meta_path):
    from sociobridge_checker import check, SELECT_ORDER
    meta = json.load(open(meta_path, encoding="utf-8"))
    picks = []
    for no in dict.fromkeys(r["no"] for r in rows):
        cand = {r["cond"]: r for r in rows if r["no"] == no}
        pick = next((cand[c] for c in SELECT_ORDER
                     if c in cand and not check(cand[c]["out"], meta[str(no)], cand[c]["th"])),
                    cand["Full Context"])
        picks.append(pick)
    return picks


def main(in_path, out_path, meta_path="data/checker_metadata.json"):
    rows = json.load(open(in_path, encoding="utf-8"))
    for r in rows:
        if "errors" in r:
            tq = mqm_tq(r["errors"], ref_words(r))
            assert abs(round(tq, 1) - float(r["mqm"])) < 0.06,                 f"errors of sentence {r['no']} / {r['cond']} give TQ {tq:.1f}, stored {r['mqm']}"
    by_cond = OrderedDict()
    for r in rows:
        by_cond.setdefault(r["cond"], []).append(r)
    by_cond["Full Context + Check/Select"] = selected_rows(rows, meta_path)

    table = []
    for cond, rs in by_cond.items():
        hyp = [r["out"] for r in rs]
        ref = [[r["ref"] for r in rs]]
        row = {
            "condition": cond,
            "n": len(rs),
            "bleu": round(sacrebleu.corpus_bleu(hyp, ref).score, 2),
            "chrf": round(sacrebleu.corpus_chrf(hyp, ref).score, 1),
            "chrf++": round(sacrebleu.corpus_chrf(hyp, ref, word_order=2).score, 1),
        }
        if all("errors" in r for r in rs):
            row["pooled_mqm_tq"] = round(pooled_tq(rs), 1)
        if all("mqm" in r for r in rs):
            row["mean_mqm_tq"] = round(statistics.mean(r["mqm"] for r in rs), 1)
        if all("acc" in r for r in rs):
            row["accurate"] = f"{sum(r['acc'] == 'Accurate' for r in rs)}/{len(rs)}"
        table.append(row)

    fields = list(OrderedDict.fromkeys(k for row in table for k in row))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(table)
    for row in table:
        print(row)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
