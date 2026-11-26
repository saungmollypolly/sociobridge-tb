"""Prompt templates for the five experimental conditions (Observe stage).

Conditions
----------
zero_shot     : Thai sentence only (baseline)
full_context  : all metadata blocks
no_hierarchy  : full context without <social_hierarchy>
no_distance   : full context without <social_distance>
no_intent     : full context without <communicative_intent>

Each ablation uses exactly the Full Context template with one block removed
from <context> and its clause removed from <instruction>.
"""
from xml.sax.saxutils import escape

CONDITIONS = ["zero_shot", "full_context", "no_hierarchy", "no_distance", "no_intent"]

CONDITION_LABELS = {
    "zero_shot": "Zero-Shot",
    "full_context": "Full Context",
    "no_hierarchy": "Ablation: No Social Hierarchy",
    "no_distance": "Ablation: No Social Distance",
    "no_intent": "Ablation: No Communicative Intent",
}

OUTPUT_FORMAT = (
    "Answer ONLY in this XML format, with no other text:\n"
    "<result><translation>...</translation>"
    "<social_markers>...</social_markers></result>"
)


def zero_shot_prompt(s):
    return f"Translate this Thai sentence into Burmese:\n{s['th']}"


def context_prompt(s, drop=None, decision=None):
    """Build the XML context prompt. `drop` is one of
    None, 'hierarchy', 'distance', 'intent'. `decision` is the optional
    committed politeness level from the Decide stage: {'level', 'reason'}."""
    sh = s["social_hierarchy"]
    lines = ["<translation_task>", "  <context>",
             f"    <setting>{escape(s['setting'])}</setting>",
             f"    <speaker role=\"{escape(s['speaker']['role'])}\" gender=\"{escape(s['speaker']['gender'])}\"/>",
             f"    <listener role=\"{escape(s['listener']['role'])}\" gender=\"{escape(s['listener']['gender'])}\"/>"]
    if drop != "hierarchy":
        lines += ["    <social_hierarchy>",
                  f"      <direction>{sh['direction']}</direction>",
                  f"      <relative_age>{sh['relative_age']}</relative_age>",
                  f"      <relative_status>{sh['relative_status']}</relative_status>",
                  "    </social_hierarchy>"]
    if drop != "distance":
        lines.append(f"    <social_distance>{s['social_distance']}</social_distance>")
    if drop != "intent":
        lines.append(f"    <communicative_intent>{s['communicative_intent']}</communicative_intent>")
    lines.append("  </context>")
    if decision:
        lines.append(f"  <politeness_decision level=\"{escape(decision['level'])}\">"
                     f"{escape(decision['reason'])}</politeness_decision>")
    lines.append(f"  <source_text lang=\"th\">{escape(s['th'])}</source_text>")

    clauses = []
    if drop != "hierarchy":
        clauses.append("the social hierarchy relationship")
    if drop != "distance":
        clauses.append("the social distance")
    if drop != "intent":
        clauses.append("the communicative intent")
    reflect = ", ".join(clauses[:-1]) + (" and " if len(clauses) > 1 else "") + clauses[-1]
    follow = " Follow the committed politeness_decision." if decision else ""
    instruction = (f"Translate the source_text from Thai into Burmese, reflecting the speaker and listener "
                   f"roles and genders, {reflect} described above. Choose the Burmese pronouns, address "
                   f"terms and sentence-final particles that fit this relationship.{follow} {OUTPUT_FORMAT}")
    lines += [f"  <instruction>{instruction}</instruction>", "</translation_task>"]
    return "\n".join(lines)


def build_prompt(sentence, condition):
    if condition == "zero_shot":
        return zero_shot_prompt(sentence)
    drop = {"full_context": None, "no_hierarchy": "hierarchy",
            "no_distance": "distance", "no_intent": "intent"}[condition]
    return context_prompt(sentence, drop)
