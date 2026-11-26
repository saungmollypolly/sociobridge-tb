"""Score translations per condition: BLEU, chrF, chrF++ (corpus level, sacreBLEU)
plus MQM aggregates (mean sentence TQ, number of Accurate sentences).

MQM sentence score:  TQ = 100 - (sum_i n_i * w_i) / N * 100
where N is the word count of the human reference.

Usage:
    python src/score.py data/pilot_outputs.json results/scores.csv
"""
import csv
import json
import statistics
import sys
from collections import OrderedDict

import sacrebleu

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


def main(in_path, out_path):
    rows = json.load(open(in_path, encoding="utf-8"))
    by_cond = OrderedDict()
    for r in rows:
        by_cond.setdefault(r["cond"], []).append(r)

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
