"""SocioBridge-TB web app (Streamlit).

Run:  streamlit run app.py
"""
import csv
import html
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline as pl  # noqa: E402
from workbook import load_workbook_sentences, DEFAULT_PATH  # noqa: E402

DEFAULT_MODEL = "gemini-3.5-flash"
REPO_URL = "https://github.com/saungmollypolly/sociobridge-tb"
SETTINGS = ["Workplace", "Education"]
GENDERS = ["Male", "Female", "Unknown"]
DIRECTIONS = ["Upward", "Equal", "Downward"]
AGES = ["Older", "Same", "Younger"]
STATUSES = ["Higher", "Equal", "Lower"]
DISTANCES = ["Close", "Familiar", "Unfamiliar"]
BASE_ROLES = ["Employee", "Student", "Manager", "Professor", "Teacher", "Colleague", "Boss",
              "Advisor/Senior person"]
BASE_INTENTS = ["Request", "Instruction", "Greeting", "Apology", "Thanking", "Invitation", "Information"]
PAGES = ["Translate", "Compare", "Candidate selection", "Results", "About"]

st.set_page_config(page_title="SocioBridge-TB", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Myanmar:wght@400;600&family=Noto+Sans+Thai:wght@400;600&display=swap');
[data-testid="stAppDeployButton"], footer {display: none !important;}
header[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 2rem; max-width: 1100px;}

/* header: site name left, navigation right */
.site-name {font-size: 1.7rem !important; font-weight: 700; margin: 0 !important; line-height: 1.2 !important;}
.site-sub {margin: 2px 0 0 !important; opacity: .7;}
.st-key-nav [role="radiogroup"] {justify-content: flex-end; gap: 26px;}
.st-key-nav label[data-testid="stRadioOption"] > div > div:first-child {display: none;}
.st-key-nav label[data-testid="stRadioOption"] {padding: 4px 0; border-bottom: 2px solid transparent;
                                                margin: 0; cursor: pointer;}
.st-key-nav label[data-testid="stRadioOption"][data-selected="true"] {border-bottom-color: currentColor;}
.st-key-nav label[data-testid="stRadioOption"][data-selected="true"] p {font-weight: 600;}
.site-rule {border: 0; border-top: 1px solid rgba(128, 128, 128, .3); margin: 6px 0 0;}
h3.sec:first-of-type {margin-top: 8px;}

h3.sec {font-size: 1.2rem; font-weight: 700; margin: 28px 0 8px;}
.mm {font-family: 'Noto Sans Myanmar', 'Myanmar Text', sans-serif; font-size: 1.5rem; line-height: 1.9;}
.quiet {opacity: .7;}
.pass {color: #2E8B3E; font-weight: 600;}
.fail {color: #D33A32; font-weight: 600;}
table.rules {border-collapse: collapse; width: 100%; font-size: .95rem;}
table.rules th, table.rules td {text-align: left; padding: 7px 10px; border-bottom: 1px solid rgba(128, 128, 128, .25);}
table.rules th {font-weight: 600; opacity: .8;}
/* translator panels */
.tr-grid {display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 8px;}
@media (max-width: 800px) {.tr-grid {grid-template-columns: 1fr;}}
.tr-panel {border: 1px solid rgba(128, 128, 128, .35); border-radius: 8px; overflow: hidden;
           display: flex; flex-direction: column;}
.tr-head {display: flex; justify-content: space-between; align-items: center; padding: 10px 16px;
          border-bottom: 1px solid rgba(128, 128, 128, .25); background: rgba(128, 128, 128, .07);
          font-size: .85rem; font-weight: 600;}
.tr-body {padding: 18px 16px; flex: 1;}
.tr-src {font-family: 'Noto Sans Thai', 'Leelawadee UI', sans-serif; font-size: 1.35rem; line-height: 1.8;}
.tr-scroll {max-height: 300px; overflow-y: auto; white-space: pre-wrap;}
.tr-gloss {margin-top: 16px; padding-top: 12px; border-top: 1px dashed rgba(128, 128, 128, .35); font-size: .95rem;}
.tr-gloss .tag, .tr-foot .tag {display: block; font-size: .75rem; text-transform: uppercase; letter-spacing: .04em;
                               opacity: .6; margin-bottom: 4px;}
.tr-foot {display: flex; flex-wrap: wrap; gap: 28px; padding: 10px 16px; border-top: 1px solid rgba(128, 128, 128, .25);
          font-size: .9rem;}
.tr-head .pass, .tr-head .fail {font-size: .85rem;}
.site-foot {margin-top: 48px; padding-top: 12px; border-top: 1px solid rgba(128, 128, 128, .3);
            font-size: .85rem; opacity: .7;}
</style>
""", unsafe_allow_html=True)


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


def esc(text):
    return html.escape(str(text))


def section(title):
    st.markdown(f'<h3 class="sec">{esc(title)}</h3>', unsafe_allow_html=True)


def quota_or_error(e):
    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
        st.error("Gemini quota exceeded (free tier: about 20 requests per day per model). Identical requests "
                 "are cached, so repeats are free. Turn on 'Single call' in Settings, change the model "
                 "name, or try again after the quota resets.")
    else:
        st.error(f"Request failed: {e}")


def rule_table(violations):
    """R1-R9 as a plain table, then the checker's messages."""
    bad = {r for r, _ in violations}
    rows = "".join(
        f"<tr><td>{r}</td><td>{esc(pl.RULE_NAMES[r])}</td>"
        f'<td class="{"fail" if r in bad else "pass"}">{"Fail" if r in bad else "Pass"}</td></tr>'
        for r in pl.RULE_NAMES)
    st.markdown(f'<table class="rules"><tr><th>Rule</th><th>Check</th><th>Result</th></tr>{rows}</table>',
                unsafe_allow_html=True)
    for r, msg in violations:
        st.markdown(f"**{r}**: {msg}")


def fallback_note():
    if pl.LAST_MODEL_USED[0] and pl.LAST_MODEL_USED[0] != model:
        st.caption(f"Note: '{model}' was unavailable (quota or overload), so '{pl.LAST_MODEL_USED[0]}' answered.")


def need_client():
    client = pl.get_client()
    if client is None:
        st.error("No API key found. Add GEMINI_API_KEY to .env (local) or to the app's Secrets (Streamlit Cloud).")
        st.stop()
    return client


# ------------------------------------------------------------------ settings (sidebar)
with st.sidebar:
    st.header("Settings")
    model = st.text_input("Model", DEFAULT_MODEL)
    use_decide = st.toggle("Decide stage (commit to a politeness level)", value=True)
    combined = st.toggle("Single call (Decide + Act in one request)", value=True,
                         help="Saves API quota: 1 call instead of 2.")
    use_repair = st.toggle("One-shot repair if Check flags the output", value=True)
    if pl.get_client():
        st.success("API key loaded")
    else:
        st.error("No API key found. Add GEMINI_API_KEY to .env (local) or to the app's Secrets (Streamlit Cloud).")
    if st.button("Test API connection", width='stretch'):
        try:
            with st.spinner("Connecting..."):
                reply = pl._call(pl.get_client(), model, "Reply with the single word: OK", 16, use_cache=False)
            st.success(f"Connected. Model replied: {reply.strip()}")
        except Exception as e:
            quota_or_error(e)

# ------------------------------------------------------------------ header + navigation
h_left, h_right = st.columns([2, 3], vertical_alignment="center")
with h_left:
    st.markdown('<p class="site-name">SocioBridge-TB</p>'
                '<p class="site-sub">Thai to Burmese translation with politeness control</p>',
                unsafe_allow_html=True)
with h_right:
    with st.container(key="nav"):
        page = st.radio("Page", PAGES, horizontal=True, label_visibility="collapsed")
st.markdown('<hr class="site-rule">', unsafe_allow_html=True)
if pl.get_client() is None:
    st.warning("No API key found, so translation is unavailable. The Results and About pages still work.")


# ------------------------------------------------------------------ situation form
def situation_form():
    section("Situation")
    s1, s2 = st.columns([1.4, 2])
    with s1:
        src = st.radio("Sentence source", ["Pilot (8 sentences)", "Workbook (all rows)", "Custom"],
                       horizontal=True)
    pool = load_pilot() if src.startswith("Pilot") else (load_wb() if src.startswith("Workbook") else [])
    labels = {f"#{s['no']} [{s['social_hierarchy']['direction']}] {s['th'][:60]}": s for s in pool}
    with s2:
        choice = st.selectbox("Sentence", list(labels)) if labels else None
    if src.startswith("Workbook") and not pool:
        st.warning("The data-collection workbook is not available here (participant data is kept offline; "
                   f"locally it is read from {DEFAULT_PATH}). Use the Pilot or Custom source.")
    p = labels.get(choice) if choice else None
    if p and p.get("validated") != "Y" and src.startswith("Workbook"):
        st.caption("Note: this row is not marked Validated (Y) in the workbook.")

    roles = opts(BASE_ROLES, [x for s in pool for x in (s["speaker"]["role"], s["listener"]["role"])])
    intents = opts(BASE_INTENTS, [s["communicative_intent"] for s in pool])

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        sp_role = st.selectbox("Speaker role", roles, idx(roles, p and p["speaker"]["role"]), key=f"sr{choice}")
        sp_gender = st.selectbox("Speaker gender", GENDERS, idx(GENDERS, p and p["speaker"]["gender"]), key=f"sg{choice}")
    with c2:
        li_role = st.selectbox("Listener role", roles, idx(roles, p and p["listener"]["role"], 2), key=f"lr{choice}")
        li_gender = st.selectbox("Listener gender", GENDERS, idx(GENDERS, p and p["listener"]["gender"], 2), key=f"lg{choice}")
    with c3:
        direction = st.selectbox("Hierarchy direction", DIRECTIONS,
                                 idx(DIRECTIONS, p and p["social_hierarchy"]["direction"]), key=f"d{choice}")
        age = st.selectbox("Listener relative age", AGES, idx(AGES, p and p["social_hierarchy"]["relative_age"]), key=f"a{choice}")
    with c4:
        status = st.selectbox("Listener relative status", STATUSES,
                              idx(STATUSES, p and p["social_hierarchy"]["relative_status"]), key=f"st{choice}")
        dist = st.selectbox("Social distance", DISTANCES, idx(DISTANCES, p and p["social_distance"], 1), key=f"di{choice}")
    t1, t2, t3 = st.columns([1, 1, 2])
    with t1:
        setting = st.selectbox("Setting", SETTINGS, idx(SETTINGS, p and p["setting"]), key=f"set{choice}")
    with t2:
        intent = st.selectbox("Communicative intent", intents,
                              idx(intents, p and p["communicative_intent"]), key=f"in{choice}")
    with t3:
        th = st.text_area("Thai sentence", value=p["th"] if p else "", height=80, key=f"th{choice}")
    if p:
        st.caption(f"English meaning: {p['en']}")
        st.caption(f"Human reference: {p['ref_my']}")
    sentence = {"setting": setting, "th": th.strip(),
                "speaker": {"role": sp_role, "gender": sp_gender},
                "listener": {"role": li_role, "gender": li_gender},
                "social_hierarchy": {"direction": direction, "relative_age": age, "relative_status": status},
                "social_distance": dist, "communicative_intent": intent}
    return sentence, p


# ---------------------------------------------------------------- page: translate
if page == "Translate":
    s, p = situation_form()
    if st.button("Translate", type="primary", disabled=not s["th"]):
        client = need_client()
        try:
            with st.spinner("Translating..."):
                t = pl.translate(s, model, use_decide, use_repair, client, combined)
        except Exception as e:
            quota_or_error(e)
            st.stop()

        n_rules = len(pl.RULE_NAMES)
        n_bad = len({r for r, _ in t["final_violations"]})
        status = (f'<span class="pass">{n_rules} of {n_rules} rules passed</span>' if t["passed"]
                  else f'<span class="fail">{n_bad} of {n_rules} rules failed</span>')
        level = t["decide"]["level"] if t["decide"] else "Not decided (stage off)"
        used = pl.LAST_MODEL_USED[0] or model
        meaning = f'<div class="tr-gloss"><span class="tag">Intended meaning</span>{esc(p["en"])}</div>' if p else ""
        section("Translation")
        st.html(f"""
<div class="tr-grid">
  <div class="tr-panel">
    <div class="tr-head"><span>Thai</span><span class="quiet">Input</span></div>
    <div class="tr-body"><div class="tr-src">{esc(s["th"])}</div>{meaning}</div>
    <div class="tr-foot">
      <div><span class="tag">Speaker</span>{esc(s["speaker"]["role"])} ({esc(s["speaker"]["gender"])})</div>
      <div><span class="tag">Listener</span>{esc(s["listener"]["role"])}</div>
      <div><span class="tag">Direction</span>{esc(s["social_hierarchy"]["direction"])}</div>
      <div><span class="tag">Intent</span>{esc(s["communicative_intent"])}</div>
    </div>
  </div>
  <div class="tr-panel">
    <div class="tr-head"><span>Burmese</span>{status}</div>
    <div class="tr-body">
      <div class="mm">{esc(t["final"])}</div>
      <div class="tr-gloss"><span class="tag">English meaning</span>{esc(t["english"])}</div>
    </div>
    <div class="tr-foot">
      <div><span class="tag">Politeness level</span><b>{esc(level)}</b></div>
      <div><span class="tag">Model</span>{esc(used)}</div>
      <div><span class="tag">Repair</span>{"Used once" if t["repaired"] else "Not needed"}</div>
    </div>
  </div>
</div>""")
        if t["decide"]:
            with st.expander("Why this politeness level?"):
                st.write(f"Candidates considered: {', '.join(t['decide']['candidates'])}.")
                st.write(t["decide"]["reason"])

        section("Rule check")
        rule_table(t["final_violations"])
        if t["repaired"]:
            with st.expander("First attempt (before repair)"):
                st.markdown(f'<div class="mm" style="font-size:1.15rem">{esc(t["first_output"])}</div>',
                            unsafe_allow_html=True)
                st.write("Failed: " + ", ".join(r for r, _ in t["first_violations"]))
        with st.expander("Prompt sent to the model"):
            st.code(t["prompt"], language="xml")

# ---------------------------------------------------------------- page: compare
elif page == "Compare":
    s, p = situation_form()
    st.caption("Translates the same sentence twice: without the situation and with it.")
    if st.button("Compare", type="primary", disabled=not s["th"]):
        client = need_client()
        try:
            with st.spinner("Translating with and without the situation..."):
                cmp_ = pl.compare(s, model, client)
        except Exception as e:
            quota_or_error(e)
            st.stop()
        zs, fc = cmp_["zero_shot"], cmp_["full_context"]

        def panel(title, out_text, en, viol):
            n = len(viol)
            label = "No rules broken" if n == 0 else f"{n} rule{'s' if n > 1 else ''} broken"
            failed = ", ".join(r for r, _ in viol) or "None"
            return f"""
  <div class="tr-panel">
    <div class="tr-head"><span>{title}</span><span class="{"fail" if n else "pass"}">{label}</span></div>
    <div class="tr-body">
      <div class="mm tr-scroll" style="font-size:1.2rem">{esc(out_text)}</div>
      <div class="tr-gloss"><span class="tag">English meaning</span><div class="tr-scroll">{esc(en)}</div></div>
    </div>
    <div class="tr-foot"><div><span class="tag">Failed rules</span>{failed}</div></div>
  </div>"""

        section("Result")
        st.html('<div class="tr-grid">'
                + panel("Without the situation", zs["out"], zs["english"], zs["violations"])
                + panel("With the situation", fc["out"], fc["english"], fc["violations"])
                + "</div>")
        with st.expander("Rule details"):
            for title, viol in (("Without the situation", zs["violations"]), ("With the situation", fc["violations"])):
                st.markdown(f"**{title}**")
                for r, msg in viol:
                    st.markdown(f"- **{r}** ({pl.RULE_NAMES[r]}): {msg}")
                if not viol:
                    st.write("No rules broken.")
        if p:
            with st.expander("Human reference"):
                st.write(p["ref_my"])
        fallback_note()

# ---------------------------------------------------------------- page: candidate selection
elif page == "Candidate selection":
    s, p = situation_form()
    st.caption("Generates four candidates (full situation and three versions with one field removed), checks "
               "each against the nine rules, and keeps the first one that passes. Full context has priority; "
               "if all fail, the one with the fewest failures is kept. Uses 4 API calls.")
    if st.button("Generate and select", type="primary", disabled=not s["th"]):
        client = need_client()
        try:
            with st.spinner("Generating 4 candidates..."):
                r = pl.select_candidates(s, model, client)
        except Exception as e:
            quota_or_error(e)
            st.stop()
        names = {"full_context": "Full context", "no_hierarchy": "No hierarchy",
                 "no_distance": "No distance", "no_intent": "No intent"}
        sel = r["selected"]
        section("Result")
        st.write(f"Selected: **{names[sel['condition']]}**" if r["any_passed"]
                 else "No candidate passed all rules, so the one with the fewest failures was kept.")
        for c in r["candidates"]:
            status_txt = ", ".join(v[0] for v in c["violations"]) or "all rules passed"
            with st.expander(f"{names[c['condition']]}: {status_txt}" + (" (selected)" if c is sel else ""),
                             expanded=c is sel):
                st.markdown(f'<div class="mm" style="font-size:1.15rem">{esc(c["out"])}</div>',
                            unsafe_allow_html=True)
                st.write(c["english"])
                for rule, msg in c["violations"]:
                    st.write(f"- **{rule}** ({pl.RULE_NAMES[rule]}): {msg}")
        fallback_note()

# ---------------------------------------------------------------- page: results
elif page == "Results":
    st.write("Pilot study: Gemini 3.6 Flash, 8 sentences, 5 prompt conditions. No API calls are needed here.")
    sc = ROOT / "results" / "scores.csv"
    cr = ROOT / "results" / "checker_results.json"
    if sc.exists():
        rows = list(csv.DictReader(open(sc, encoding="utf-8-sig")))
        section("Scores by condition")
        st.dataframe(rows, hide_index=True, width='stretch')
        left, right = st.columns(2)
        with left:
            st.caption("Mean MQM-inspired quality score")
            st.bar_chart({r["condition"]: float(r["mean_mqm_tq"]) for r in rows})
        with right:
            st.caption("chrF (ranks the conditions differently from the human scores)")
            st.bar_chart({r["condition"]: float(r["chrf"]) for r in rows})
    if cr.exists():
        import sociobridge_checker as chk
        res = json.load(open(cr, encoding="utf-8"))
        e = chk.evaluate(res)
        section("Rule checker compared with human labels")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Precision", f"{e['precision']:.2f}")
        m2.metric("Recall", f"{e['recall']:.2f}")
        m3.metric("F1", f"{e['f1']:.2f}")
        m4.metric("TP / FP / FN / TN", f"{e['tp']}/{e['fp']}/{e['fn']}/{e['tn']}")
        picks = chk.select(res)
        acc = sum(r["acc"] == "Accurate" for r in picks)
        st.write(f"Checker-guided selection: {acc} of {len(picks)} accurate, mean quality score "
                 f"{sum(r['mqm'] for r in picks) / len(picks):.1f}. These figures are in-sample: the rules "
                 "were written on the same sentences.")
        section("Failures per condition")
        conds = list(dict.fromkeys(r["cond"] for r in res))
        st.table([{"Condition": c,
                   "Flagged": f"{sum(r['flagged'] for r in res if r['cond'] == c)}/8",
                   "Rule failures": sum(len(r['violations']) for r in res if r['cond'] == c)} for c in conds])
        with st.expander("All 40 outputs with checker results"):
            st.dataframe([{"No": r["no"], "Condition": r["cond"], "Human label": r.get("acc"),
                           "Flagged": r["flagged"], "Rules": " ".join(v[0] for v in r["violations"]),
                           "Output": r["out"][:120]} for r in res], hide_index=True)

# ---------------------------------------------------------------- page: about
else:
    section("What this is")
    st.write("SocioBridge-TB translates Thai sentences into Burmese and tries to use the right level of "
             "politeness: the right polite ending, the right title for the listener, and the right word for "
             "\"I\". A normal machine translator does not know who is speaking to whom, so it often gets "
             "these words wrong.")
    section("How it works")
    st.markdown(
        "1. **Observe.** You describe the situation: who is speaking, who is listening, and their relationship.\n"
        "2. **Decide.** The system chooses one politeness level, for example Formal.\n"
        "3. **Act.** A language model (Gemini) translates the sentence with this information.\n"
        "4. **Check.** Nine rules test the result. If a rule fails, the system repairs the translation once.")
    section("Limits")
    st.write("The rules were written from a small pilot of 8 sentences and are too strict for natural Burmese: "
             "on 50 new human-written sentences they rejected 32. Treat a failed rule as something to review, "
             "not as a final judgement.")
    section("Using this site")
    st.write("Settings (model, stages, API test) are in the panel on the left. Light and dark mode are in the "
             "menu at the top right.")

st.markdown(f'<div class="site-foot">SocioBridge-TB, term project for CPE 663 Cognitive Computing, KMUTT. '
            f'<a href="{REPO_URL}" target="_blank">Source code on GitHub</a></div>', unsafe_allow_html=True)
