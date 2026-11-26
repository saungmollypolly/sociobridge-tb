"""SocioBridge-TB pipeline: Observe -> Decide -> Act -> Check.

Used by app.py. Each LLM call is a fresh, stateless request.

Speed design (the web app should answer in a few seconds):
  * identical requests are served from a disk cache (instant, no quota);
  * models that just failed (quota / overload / timeout) are skipped for a while;
  * the English explanation is produced in the SAME call as the translation;
  * independent calls (candidates, zero-shot vs full context) run in parallel.
"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from prompts import context_prompt, zero_shot_prompt, OUTPUT_FORMAT
from sociobridge_checker import check, MAPPING_LIBRARY, ADDRESS_TERMS
from run_experiment import parse_translation

ROOT = Path(__file__).resolve().parent.parent

RULE_NAMES = {
    "R1": "Single sentence, no commentary/markdown",
    "R2": "No Thai script in output",
    "R3": "No unresolved alternatives",
    "R4": "Required polite final particle",
    "R5": "No wrong-gender final particle",
    "R6": "Address term matches listener role",
    "R7": "Self-reference fits gender/hierarchy",
    "R8": "No casual pronoun in upward speech",
    "R9": "Numbers preserved",
}

LEVELS = {
    "Formal": "polite pronouns, role-based address term, gendered polite final particle",
    "Neutral": "polite verb endings, little or no honorific marking",
    "Casual": "casual pronouns and plain endings (only for close equal/downward speech)",
}

# Output format used by the app: the translation plus a literal English gloss, so a
# reader who does not know Burmese can see which honorifics were chosen.
GLOSS_FORMAT = (
    "Answer ONLY in this XML format, with no other text:\n"
    "<result><translation>BURMESE TRANSLATION</translation>"
    "<english>literal English meaning of your Burmese translation, followed by a bracketed gloss of "
    "the markers used, e.g. [self: humble female 'daughter'] [address: 'Manager'] "
    "[ending: polite female]</english></result>")

GLOSS_MISSING = "(English explanation unavailable)"


def get_client():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:  # Streamlit Cloud: the key is stored as a secret, not in .env
        try:
            import streamlit as st
            key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            key = ""
    if not key:
        return None
    from google import genai
    from google.genai import types
    # Short timeout, one attempt: the fallback logic below handles failures quickly.
    return genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=12000, retry_options=types.HttpRetryOptions(attempts=1)))


FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite",
                   "gemini-3.7-flash", "gemini-3.8-flash"]
LAST_MODEL_USED = [""]
STRICT = False   # experiments set this True: no model fallback
CACHE_PATH = ROOT / "results" / "llm_cache.json"
_cache = None
_lock = threading.Lock()
_dead = {}   # model -> time until which it is skipped


def _cache_load():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def _mark_dead(model, err):
    """Skip a failing model for a while so later calls do not wait for it again."""
    e = str(err)
    if "404" in e or "NOT_FOUND" in e:
        secs = 86400
    elif "429" in e or "RESOURCE_EXHAUSTED" in e:
        secs = 600
    else:                      # 503 overload / 504 timeout
        secs = 60
    _dead[model] = time.time() + secs


def _is_dead(model):
    return _dead.get(model, 0) > time.time()


def _generate(client, m, prompt, max_tokens):
    from google.genai import types
    cfg = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0))
    try:
        return client.models.generate_content(model=m, contents=prompt, config=cfg).text or ""
    except Exception as e:
        if "400" not in str(e) and "INVALID_ARGUMENT" not in str(e):
            raise
        # some models (e.g. flash-lite) reject thinking_budget=0: retry without it
        plain = types.GenerateContentConfig(max_output_tokens=max_tokens)
        return client.models.generate_content(model=m, contents=prompt, config=plain).text or ""


def _call(client, model, prompt, max_tokens=512, use_cache=True):
    """One stateless LLM call with disk cache and model fallback."""
    import hashlib
    key = hashlib.sha256(f"{model}|{max_tokens}|{prompt}".encode("utf-8")).hexdigest()
    cache = _cache_load()
    if use_cache and key in cache:
        return cache[key]
    skippable = ("429", "503", "504", "404", "RESOURCE_EXHAUSTED",
                 "UNAVAILABLE", "DEADLINE_EXCEEDED", "NOT_FOUND", "deadline")
    # STRICT (used for experiments): only the requested model, so results are never mixed
    # across models. A quota error (429) is raised at once; overload is retried.
    chain = [model] if STRICT else [model] + [f for f in FALLBACK_MODELS if f != model]
    text, err = "", None
    for round_ in range(5 if STRICT else 2):
        live = [m for m in chain if not _is_dead(m)] or chain   # if all are dead, try anyway
        for m in live:
            try:
                text = _generate(client, m, prompt, max_tokens)
                LAST_MODEL_USED[0] = m
                break
            except Exception as e:
                if STRICT and ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)):
                    raise
                if not any(c in str(e) for c in skippable):
                    raise
                err = e
                if not STRICT:
                    _mark_dead(m, e)
        if text:
            break
        time.sleep(5 if STRICT else 0.5)
    else:
        raise err
    if use_cache and text:
        with _lock:
            cache[key] = text
            CACHE_PATH.parent.mkdir(exist_ok=True)
            CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return text


def parse_english(raw):
    m = re.search(r"<english>(.*?)</english>", raw, re.S)
    return m.group(1).strip() if m else ""


def with_gloss(prompt):
    """Swap the plain output format for the translation + English gloss format."""
    return prompt.replace(OUTPUT_FORMAT, GLOSS_FORMAT)


# ---------------------------------------------------------------- Observe
def observe(s):
    """Return (prompt-ready sentence dict, checker metadata)."""
    meta = {"direction": s["social_hierarchy"]["direction"],
            "speaker_gender": s["speaker"]["gender"],
            "listener_role": s["listener"]["role"] if s["listener"]["role"] in ADDRESS_TERMS else None}
    return s, meta


# ----------------------------------------------------------------- Decide
def candidate_levels(s):
    """Mapping Library proposes 2-3 candidate politeness levels."""
    d = s["social_hierarchy"]["direction"]
    if d == "Upward":
        return ["Formal", "Neutral"]
    if d == "Equal":
        return ["Neutral", "Casual", "Formal"] if s["social_distance"] == "Close" else ["Neutral", "Formal"]
    return ["Neutral", "Casual"]


def decide(client, model, s):
    """Commitment step: the model compares candidate levels and commits to one."""
    cands = candidate_levels(s)
    desc = "\n".join(f"- {c}: {LEVELS[c]}" for c in cands)
    prompt = (
        "You decide the politeness level for a Thai->Burmese translation.\n"
        f"Speaker: {s['speaker']['role']} ({s['speaker']['gender']}). "
        f"Listener: {s['listener']['role']} ({s['listener']['gender']}).\n"
        f"Hierarchy: {s['social_hierarchy']['direction']}, listener is "
        f"{s['social_hierarchy']['relative_age']} / {s['social_hierarchy']['relative_status']}. "
        f"Distance: {s['social_distance']}. Intent: {s['communicative_intent']}. Setting: {s['setting']}.\n"
        f"Candidate levels:\n{desc}\n"
        "Compare the candidates and commit to exactly ONE. Answer ONLY as JSON: "
        '{"level": "<one candidate>", "reason": "<one short sentence>"}')
    raw = _call(client, model, prompt, 200)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        d = json.loads(m.group(0))
        if d["level"] in cands:
            return {"level": d["level"], "reason": d["reason"], "candidates": cands}
    except Exception:
        pass
    # deterministic fallback: first (most conventional) candidate
    return {"level": cands[0], "reason": "Mapping Library default for this hierarchy.", "candidates": cands}


# -------------------------------------------------------------------- Act
def act(client, model, s, decision=None, drop=None):
    """Translate. Returns (prompt, raw, burmese, english)."""
    prompt = with_gloss(context_prompt(s, drop=drop, decision=decision))
    raw = _call(client, model, prompt)
    return prompt, raw, parse_translation(raw), parse_english(raw)


def act_combined(client, model, s):
    """Decide + Act in ONE call: the model commits to a level, then translates.
    Returns (decision, prompt, raw, burmese, english)."""
    cands = candidate_levels(s)
    prompt = context_prompt(s).replace(
        OUTPUT_FORMAT,
        f"First compare the politeness levels {', '.join(cands)} and commit to exactly one with a "
        "one-sentence reason, then translate accordingly. Answer ONLY in this XML format, with no other "
        "text: <result><decision level=\"...\">reason</decision><translation>BURMESE TRANSLATION</translation>"
        "<english>literal English meaning of your Burmese translation, followed by a bracketed gloss of the "
        "markers used, e.g. [self: humble female 'daughter'] [address: 'Manager'] [ending: polite female]"
        "</english></result>")
    raw = _call(client, model, prompt)
    m = re.search(r'<decision level="([^"]*)">(.*?)</decision>', raw, re.S)
    decision = {"level": m.group(1), "reason": m.group(2).strip(), "candidates": cands} if m else \
        {"level": "?", "reason": "Model did not return a decision.", "candidates": cands}
    return decision, prompt, raw, parse_translation(raw), parse_english(raw)


def zero_shot(client, model, s):
    """Baseline: Thai sentence only, no social context. The prompt is kept unchanged so the
    baseline behaves as in the paper; its English gloss is a separate follow-up call."""
    prompt = zero_shot_prompt(s)
    raw = _call(client, model, prompt)
    return {"prompt": prompt, "raw": raw, "out": raw.strip(), "violations": run_check(raw.strip(), s)}


def back_translate(client, model, burmese):
    """Literal English gloss of a Burmese text (used for the zero-shot baseline, and as a
    fallback when the model forgot the <english> tag)."""
    prompt = (
        "Translate this Burmese text into English as literally as possible, so a reader can see "
        "exactly which pronouns, address terms and politeness particles it uses. After the "
        "translation, add a bracketed gloss of each marker, e.g. [self: humble female 'daughter'], "
        "[address: 'Manager' / generic 'teacher'], [ending: polite male / polite female]. "
        "If the text contains commentary or alternatives, say so in one line. "
        "Answer in English only, no Burmese script. Start directly with the translation, "
        "no introduction.\n\n" + burmese)
    return _call(client, model, prompt, 400).strip()


def ensure_english(client, model, burmese, english):
    return english or back_translate(client, model, burmese)


# ------------------------------------------------------------------ Check
def run_check(out, s):
    _, meta = observe(s)
    return check(out, meta, s["th"])


def repair(client, model, s, decision, bad_out, violations):
    """One targeted repair. Returns (burmese, english)."""
    listed = "; ".join(f"{r}: {RULE_NAMES[r]}" for r, _ in violations)
    _, meta = observe(s)
    lib = MAPPING_LIBRARY.get((meta["direction"], meta["speaker_gender"]), {})
    hints = []
    if lib.get("final_particle"):
        hints.append("end with " + " or ".join(lib["final_particle"]))
    if lib.get("forbidden_particle"):
        hints.append("never use " + " or ".join(lib["forbidden_particle"]))
    if meta["listener_role"]:
        hints.append("address the listener as " + " or ".join(ADDRESS_TERMS[meta["listener_role"]]))
    required = f"  <required_markers>{'; '.join(hints)}</required_markers>\n" if hints else ""
    prompt = with_gloss(context_prompt(s, decision=decision)).replace(
        "</translation_task>",
        f"  <previous_translation>{bad_out}</previous_translation>\n"
        f"  <violated_rules>{listed}</violated_rules>\n{required}"
        "  <repair>Fix only the violated rules and answer in the same XML format.</repair>\n"
        "</translation_task>")
    raw = _call(client, model, prompt)
    return parse_translation(raw), parse_english(raw)


SELECT_CONDITIONS = [("full_context", None), ("no_hierarchy", "hierarchy"),
                     ("no_distance", "distance"), ("no_intent", "intent")]


def select_candidates(s, model, client=None):
    """Generate -> evaluate -> select: translate under context-bearing conditions (in
    parallel), check each, and release the first unflagged one (Full Context first), else the one with the fewest violations."""
    client = client or get_client()

    def one(item):
        name, drop = item
        _, _, out, en = act(client, model, s, None, drop)
        v = run_check(out, s)
        return {"condition": name, "out": out, "english": en, "violations": v, "flagged": bool(v)}

    with ThreadPoolExecutor(max_workers=len(SELECT_CONDITIONS)) as ex:
        cands = list(ex.map(one, SELECT_CONDITIONS))
    for c in cands:
        c["english"] = ensure_english(client, model, c["out"], c["english"])
    # first unflagged candidate; if all are flagged, the one with the fewest violations (ties: first)
    pick = next((c for c in cands if not c["flagged"]), None) or min(cands, key=lambda c: len(c["violations"]))
    return {"candidates": cands, "selected": pick, "any_passed": not pick["flagged"]}


def compare(s, model, client=None):
    """Zero-Shot vs Full Context for one sentence; the two calls run in parallel."""
    client = client or get_client()
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_zs = ex.submit(zero_shot, client, model, s)
        f_fc = ex.submit(act, client, model, s)
        zs, (_, _, fc_out, fc_en) = f_zs.result(), f_fc.result()
    with ThreadPoolExecutor(max_workers=2) as ex:
        g_zs = ex.submit(back_translate, client, model, zs["out"])
        g_fc = ex.submit(ensure_english, client, model, fc_out, fc_en)
        zs_en, fc_en = g_zs.result(), g_fc.result()
    return {"zero_shot": {**zs, "english": zs_en},
            "full_context": {"out": fc_out, "english": fc_en, "violations": run_check(fc_out, s)}}


def translate(s, model, use_decide=True, use_repair=True, client=None, combined=False):
    """Run the full cycle and return a trace dict (includes 'english' for the final output).
    combined=True merges Decide and Act (and the English gloss) into a single API call."""
    client = client or get_client()
    trace = {"observe": s}
    if combined and use_decide:
        decision, prompt, raw, out, english = act_combined(client, model, s)
        trace["decide"] = decision
        decision = decision if decision["level"] != "?" else None
    else:
        decision = decide(client, model, s) if use_decide else None
        trace["decide"] = decision
        prompt, raw, out, english = act(client, model, s, decision)
    trace.update(prompt=prompt, raw=raw, first_output=out)
    viol = run_check(out, s)
    trace["first_violations"] = viol
    final, final_en, final_viol, repaired = out, english, viol, False
    if viol and use_repair:
        fixed, fixed_en = repair(client, model, s, decision, out, viol)
        fv = run_check(fixed, s)
        repaired = True
        trace["repair_output"], trace["repair_violations"] = fixed, fv
        if len(fv) < len(viol):   # keep the repair only if it is strictly better
            final, final_en, final_viol = fixed, fixed_en, fv
    final_en = ensure_english(client, model, final, final_en)
    trace.update(final=final, english=final_en, final_violations=final_viol, repaired=repaired,
                 passed=not final_viol)
    return trace
