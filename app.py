"""SocioBridge-TB web app (Streamlit).

Run:  streamlit run app.py
"""
import csv
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline as pl  # noqa: E402
from workbook import load_workbook_sentences, DEFAULT_PATH  # noqa: E402

DEFAULT_MODEL = "gemini-3.5-flash"
SETTINGS = ["Workplace", "Education"]
GENDERS = ["Male", "Female", "Unknown"]
DIRECTIONS = ["Upward", "Equal", "Downward"]
AGES = ["Older", "Same", "Younger"]
STATUSES = ["Higher", "Equal", "Lower"]
DISTANCES = ["Close", "Familiar", "Unfamiliar"]
BASE_ROLES = ["Employee", "Student", "Manager", "Professor", "Teacher", "Colleague", "Boss",
              "Advisor/Senior person"]
BASE_INTENTS = ["Request", "Instruction", "Greeting", "Apology", "Thanking", "Invitation", "Information"]

st.set_page_config(page_title="SocioBridge-TB", page_icon="🌉", layout="wide")


@st.cache_data
def load_pilot():
    return json.load(open(ROOT / "data" / "pilot_sentences.json", encoding="utf-8"))["sentences"]


@st.cache_data
def load_wb():
    return load_workbook_sentences()


def opts(base, extra):
    return list(dict.fromkeys(list(base) + [e for e in extra if e]))


def idx(options, value, default=0):
    return options.index(value) if value in options else default


def quota_or_error(e):
    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
        st.error("Gemini quota exceeded (free tier: about 20 requests/day per model). Identical requests "
                 "are cached, so repeats are free. Turn on 'Single call' in the sidebar, switch the model "
                 "name, or retry after the quota resets.")
    else:
        st.error(f"Request failed: {e}")


def rule_table(violations):
    bad = {r for r, _ in violations}
    st.table([{"Rule": r, "Check": pl.RULE_NAMES[r], "Result": "❌ violated" if r in bad else "✅ pass"}
              for r in pl.RULE_NAMES])
    for r, msg in violations:
        st.write(f"**{r}**: {msg}")


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🌉 SocioBridge-TB")
    st.caption("Thai → Burmese translation with social context")
    model = st.text_input("Model", DEFAULT_MODEL)
    use_decide = st.toggle("Decide stage (commit to a politeness level)", value=True)
    combined = st.toggle("Single call (Decide + Act in one request)", value=True,
                         help="Saves API quota: 1 call instead of 2.")
    use_repair = st.toggle("One-shot repair if Check flags the output", value=True)
    if pl.get_client():
        st.success("API key loaded")
    else:
        st.error("No API key found. Add GEMINI_API_KEY to .env (local) or to the app's Secrets (Streamlit Cloud)")
    if st.button("Test API connection", width='stretch'):
        try:
            with st.spinner("Connecting..."):
                reply = pl._call(pl.get_client(), model, "Reply with the single word: OK", 16, use_cache=False)
            st.success(f"Connected. Model replied: {reply.strip()}")
        except Exception as e:
            quota_or_error(e)

st.title("SocioBridge-TB")
st.markdown("Translate Thai into Burmese with the right level of politeness: "
            "**Observe → Decide → Act → Check**.")

tab_tr, tab_cmp, tab_sel, tab_dash = st.tabs(
    ["Translator", "Zero-Shot vs Full Context", "Candidate selection", "Experiment dashboard"])

# ------------------------------------------------- shared Observe form
src = st.radio("Sentence source", ["Pilot (8 sentences)", "Workbook (all rows)", "Custom"],
               horizontal=True)
pool = load_pilot() if src.startswith("Pilot") else (load_wb() if src.startswith("Workbook") else [])
if src.startswith("Workbook") and not pool:
    st.warning("The data-collection workbook is not available here (participant data is kept offline; "
               f"locally it is read from {DEFAULT_PATH}). Use the Pilot or Custom source.")
labels = {f"#{s['no']} [{s['social_hierarchy']['direction']}] {s['th'][:60]}": s for s in pool}
choice = st.selectbox("Sentence", list(labels)) if labels else None
p = labels.get(choice) if choice else None
if p and p.get("validated") != "Y" and src.startswith("Workbook"):
    st.caption("Note: this row is not marked Validated (Y) in the workbook.")

all_roles = opts(BASE_ROLES, [x for s in pool for x in (s["speaker"]["role"], s["listener"]["role"])])
all_intents = opts(BASE_INTENTS, [s["communicative_intent"] for s in pool])

st.subheader("1 · Observe — describe the social situation")
c1, c2, c3 = st.columns(3)
with c1:
    setting = st.selectbox("Setting", SETTINGS, idx(SETTINGS, p and p["setting"]), key=f"set{choice}")
    sp_role = st.selectbox("Speaker role", all_roles, idx(all_roles, p and p["speaker"]["role"]), key=f"sr{choice}")
    sp_gender = st.selectbox("Speaker gender", GENDERS, idx(GENDERS, p and p["speaker"]["gender"]), key=f"sg{choice}")
with c2:
    li_role = st.selectbox("Listener role", all_roles, idx(all_roles, p and p["listener"]["role"], 2), key=f"lr{choice}")
    li_gender = st.selectbox("Listener gender", GENDERS, idx(GENDERS, p and p["listener"]["gender"], 2), key=f"lg{choice}")
    direction = st.selectbox("Hierarchy direction", DIRECTIONS,
                             idx(DIRECTIONS, p and p["social_hierarchy"]["direction"]), key=f"d{choice}")
with c3:
    age = st.selectbox("Listener relative age", AGES, idx(AGES, p and p["social_hierarchy"]["relative_age"]), key=f"a{choice}")
    status = st.selectbox("Listener relative status", STATUSES,
                          idx(STATUSES, p and p["social_hierarchy"]["relative_status"]), key=f"st{choice}")
    dist = st.selectbox("Social distance", DISTANCES, idx(DISTANCES, p and p["social_distance"], 1), key=f"di{choice}")
intent = st.selectbox("Communicative intent", all_intents,
                      idx(all_intents, p and p["communicative_intent"]), key=f"in{choice}")
th = st.text_area("Thai sentence", value=p["th"] if p else "", height=80, key=f"th{choice}")
if p:
    st.caption(f"English meaning: {p['en']}  ·  Human reference: {p['ref_my']}")


def current_sentence():
    return {"setting": setting, "th": th.strip(),
            "speaker": {"role": sp_role, "gender": sp_gender},
            "listener": {"role": li_role, "gender": li_gender},
            "social_hierarchy": {"direction": direction, "relative_age": age, "relative_status": status},
            "social_distance": dist, "communicative_intent": intent}


def need_client():
    client = pl.get_client()
    if client is None:
        st.error("No API key found. Add GEMINI_API_KEY to .env (local) or to the app's Secrets (Streamlit Cloud)")
        st.stop()
    return client


# ---------------------------------------------------------------- tab: translator
with tab_tr:
    if st.button("Translate", type="primary", disabled=not th.strip()):
        client = need_client()
        try:
            with st.spinner("Observe → Decide → Act → Check..."):
                t = pl.translate(current_sentence(), model, use_decide, use_repair, client, combined)
            en_final = t["english"]
        except Exception as e:
            quota_or_error(e)
            st.stop()

        st.subheader("2 · Decide")
        if t["decide"]:
            d = t["decide"]
            st.info(f"Candidates: {', '.join(d['candidates'])}  →  committed to **{d['level']}**\n\n{d['reason']}")
        else:
            st.caption("Decide stage is switched off.")
        st.subheader("3 · Act — translation")
        st.markdown("**English meaning of the translation**")
        st.info(en_final)
        with st.expander("Burmese output", expanded=True):
            st.markdown(f"### {t['final']}")
        if pl.LAST_MODEL_USED[0] and pl.LAST_MODEL_USED[0] != model:
            st.caption(f"Note: '{model}' was unavailable (quota/overload), so '{pl.LAST_MODEL_USED[0]}' answered.")
        if t["repaired"]:
            st.caption(f"First attempt: {t['first_output']}")
        st.subheader("4 · Check — rules R1–R9")
        (st.success if t["passed"] else st.warning)(
            "All applicable rules passed. Output released." if t["passed"]
            else "Violations remain after the final attempt.")
        rule_table(t["final_violations"])
        if t["repaired"]:
            st.caption("First attempt violated: " + ", ".join(r for r, _ in t["first_violations"]))
        with st.expander("Prompt sent to the model (XML context)"):
            st.code(t["prompt"], language="xml")

# ---------------------------------------------------------------- tab: compare
with tab_cmp:
    st.write("Same sentence, with and without the social context.")
    if st.button("Compare", disabled=not th.strip()):
        client = need_client()
        s = current_sentence()
        try:
            with st.spinner("Translating with and without context..."):
                cmp_ = pl.compare(s, model, client)
            zs, zs_en = cmp_["zero_shot"], cmp_["zero_shot"]["english"]
            out, fc_en, fc_v = (cmp_["full_context"]["out"], cmp_["full_context"]["english"],
                                cmp_["full_context"]["violations"])
        except Exception as e:
            quota_or_error(e)
            st.stop()

        def violation_lines(v):
            return "\n".join(f"- **{r}** — {pl.RULE_NAMES[r]}: {msg}" for r, msg in v) or "No rule violations."

        st.markdown(f"**Thai source:** {s['th']}" + (f"  \n**Intended meaning:** {p['en']}" if p else ""))
        a, b = st.columns(2)
        with a:
            st.subheader("Zero-Shot (no context)")
            st.markdown("**English meaning of the output**")
            st.info(zs_en)
            (st.error if zs["violations"] else st.success)(violation_lines(zs["violations"]))
            with st.expander("Burmese output"):
                st.write(zs["out"])
        with b:
            st.subheader("Full Context")
            st.markdown("**English meaning of the output**")
            st.info(fc_en)
            (st.error if fc_v else st.success)(violation_lines(fc_v))
            with st.expander("Burmese output"):
                st.write(out)
        if p:
            with st.expander("Human reference"):
                st.write(p["ref_my"])
        if pl.LAST_MODEL_USED[0] and pl.LAST_MODEL_USED[0] != model:
            st.caption(f"Note: '{model}' was unavailable, so '{pl.LAST_MODEL_USED[0]}' answered.")

# ---------------------------------------------------------------- tab: select
with tab_sel:
    st.write("Generate candidates under Full Context and the three ablations, check each with R1–R9, "
             "and release the first unflagged one (Full Context has priority; if all are flagged, the one with the fewest violations). Uses 4 API calls.")
    if st.button("Generate, check and select", disabled=not th.strip()):
        client = need_client()
        try:
            with st.spinner("Generating 4 candidates..."):
                r = pl.select_candidates(current_sentence(), model, client)
            en = [c["english"] for c in r["candidates"]]
        except Exception as e:
            quota_or_error(e)
            st.stop()
        names = {"full_context": "Full Context", "no_hierarchy": "No Hierarchy",
                 "no_distance": "No Distance", "no_intent": "No Intent"}
        sel = r["selected"]
        (st.success if r["any_passed"] else st.warning)(
            f"Selected: {names[sel['condition']]}" if r["any_passed"]
            else "No candidate passed all rules; falling back to Full Context.")
        for c, e_txt in zip(r["candidates"], en):
            icon = "✅" if c is sel else ("⚠️" if c["violations"] else "•")
            with st.expander(f"{icon} {names[c['condition']]} — "
                             + (", ".join(v[0] for v in c["violations"]) or "all rules passed"),
                             expanded=c is sel):
                st.markdown("**English meaning**")
                st.info(e_txt)
                for rule, msg in c["violations"]:
                    st.write(f"- **{rule}** — {pl.RULE_NAMES[rule]}: {msg}")
                st.caption("Burmese output")
                st.write(c["out"])
        if pl.LAST_MODEL_USED[0] and pl.LAST_MODEL_USED[0] != model:
            st.caption(f"Note: '{model}' was unavailable, so '{pl.LAST_MODEL_USED[0]}' answered.")

# ---------------------------------------------------------------- tab: dashboard
with tab_dash:
    st.write("Pilot results: Gemini 3.6 Flash, 8 sentences × 5 conditions (no API calls needed).")
    sc = ROOT / "results" / "scores.csv"
    cr = ROOT / "results" / "checker_results.json"
    if sc.exists():
        rows = list(csv.DictReader(open(sc, encoding="utf-8-sig")))
        st.subheader("Scores by condition")
        st.dataframe(rows, hide_index=True, width='stretch')
        left, right = st.columns(2)
        with left:
            st.caption("Mean MQM TQ")
            st.bar_chart({r["condition"]: float(r["mean_mqm_tq"]) for r in rows})
        with right:
            st.caption("chrF (ranks conditions differently from MQM)")
            st.bar_chart({r["condition"]: float(r["chrf"]) for r in rows})
    if cr.exists():
        import sociobridge_checker as chk
        res = json.load(open(cr, encoding="utf-8"))
        e = chk.evaluate(res)
        st.subheader("Rule-based checker vs human labels")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Precision", f"{e['precision']:.2f}")
        m2.metric("Recall", f"{e['recall']:.2f}")
        m3.metric("F1", f"{e['f1']:.2f}")
        m4.metric("TP / FP / FN / TN", f"{e['tp']}/{e['fp']}/{e['fn']}/{e['tn']}")
        picks = chk.select(res)
        acc = sum(r["acc"] == "Accurate" for r in picks)
        st.write(f"Checker-guided selection: **{acc}/{len(picks)}** accurate, "
                 f"mean MQM TQ **{sum(r['mqm'] for r in picks) / len(picks):.1f}**")
        st.subheader("Violations per condition")
        conds = list(dict.fromkeys(r["cond"] for r in res))
        st.table([{"Condition": c,
                   "Flagged": f"{sum(r['flagged'] for r in res if r['cond'] == c)}/8",
                   "Violations": sum(len(r['violations']) for r in res if r['cond'] == c)} for c in conds])
        with st.expander("All 40 outputs with checker results"):
            st.dataframe([{"No": r["no"], "Condition": r["cond"], "Human label": r.get("acc"),
                           "Flagged": r["flagged"], "Rules": " ".join(v[0] for v in r["violations"]),
                           "Output": r["out"][:120]} for r in res], hide_index=True)
