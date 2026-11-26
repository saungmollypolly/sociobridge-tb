# SocioBridge-TB

**A cognitive Observe–Decide–Act–Check architecture for socio-pragmatic context injection in LLM-based Thai → Burmese translation.**

Term project for CPE 663: Cognitive Computing, King Mongkut's University of Technology Thonburi (KMUTT).
Author: Saung Hnin Wai (68070701606)

Thai and Burmese mark the speaker–listener relationship with pronouns, address terms and sentence-final particles (e.g., Thai ครับ/ค่ะ ↔ Burmese ခင်ဗျာ/ရှင့်). Without social context, LLMs often collapse the register, omit polite particles or hedge between honorifics. SocioBridge-TB:

1. **Observe**: injects structured XML social metadata (setting, roles, gender, social hierarchy, social distance, communicative intent) into the prompt;
2. **Decide**: *(designed, not yet evaluated)* commits to one politeness level;
3. **Act**: translates with an isolated, stateless LLM call;
4. **Check**: verifies the output with a rule-based politeness checker (rules R1–R9) compiled from the Socio-Pragmatic Mapping Library, then selects or repairs flagged outputs.

## Repository structure

```
sociobridge-tb/
├── README.md
├── requirements.txt
├── app.py                        # Streamlit web app (4 tabs, see "Web app")
├── .env.example                  # copy to .env and add your API key
├── data/
│   ├── pilot_sentences.json      # 8 pilot sentences + social metadata (checked against the data-collection workbook)
│   ├── pilot_outputs.json        # 40 pilot translations (8 × 5 conditions) + human labels, MQM
│   └── checker_metadata.json     # metadata used by the checker rules
├── src/
│   ├── prompts.py                # prompt templates for the 5 conditions (+ optional Decide block)
│   ├── run_experiment.py         # Observe -> Act: calls the Gemini API (paper experiment, unchanged)
│   ├── pipeline.py               # Observe -> Decide -> Act -> Check cycle used by the web app
│   ├── workbook.py               # loads sentences from the data-collection .xlsx
│   ├── score.py                  # BLEU / chrF / chrF++ / MQM aggregates
│   └── sociobridge_checker.py    # Check: Mapping Library + rules R1-R9 + selection
└── results/
    ├── scores.csv
    ├── checker_results.csv / .json
    ├── checker_summary.txt
    └── llm_cache.json            # created by the app: cached model answers (git-ignore if you like)
```

## Web app

```bash
streamlit run app.py          # opens http://localhost:8501
```

**Keep the app always running (Windows).** A scheduled task, *SocioBridge-TB app*, runs
`scripts/keep_app_running.vbs` at logon and every 5 minutes; it starts the app if nothing is listening on port
8501, so the page comes back by itself after sleep, restart or a crash (within 5 minutes). Starts and failures are
logged in `results/app_server.log`. To remove it: `Unregister-ScheduledTask -TaskName "SocioBridge-TB app"`.

Choose a sentence source in the app: **Pilot** (the 8 validated pilot sentences), **Workbook** (all rows of the
data-collection `.xlsx`; spelling variants such as "Unfamilar" are normalised, and rows not marked Validated are flagged)
or **Custom** (type any Thai sentence and set the six social dimensions yourself). The app has four tabs:

| Tab | What it does |
|---|---|
| **Translator** | Full Observe → **Decide** → Act → Check cycle. Decide proposes 2–3 politeness levels from the Mapping Library and the model commits to one with a stated reason. The result shows the **English meaning** of the translation, the rule table R1–R9, and the XML prompt. If Check flags the output, one targeted **repair** is attempted (kept only if it has strictly fewer violations). |
| **Zero-Shot vs Full Context** | The same sentence with and without social context, side by side. Each side shows the English meaning of the output (with honorific markers glossed in brackets) and the rule violations in plain English; Burmese text is in expanders. |
| **Candidate selection** | Generate → evaluate → select (paper Sec. III-F): four candidates (Full Context and the three ablations) are generated in parallel, each is checked with R1–R9, and the first unflagged one is selected (if all are flagged, the one with the fewest violations). Every candidate is shown with its English meaning and violated rules. |
| **Experiment dashboard** | Pilot results without any API call: scores per condition (MQM, BLEU, chrF), charts, checker precision / recall / F1, checker-guided selection and violations per condition. |

Sidebar options: model name, Decide on/off, **Single call** (Decide + Act + English in one request) and repair on/off.

### Speed and API quota

The app is designed to answer in a few seconds:

- **One call per translation.** The English explanation is returned in the same request as the Burmese translation, and with *Single call* the Decide step is merged in too.
- **Parallel calls.** The four candidates, and the zero-shot / full-context pair, run concurrently.
- **Cache.** Identical requests are served from `results/llm_cache.json` (instant, no quota).
- **Automatic fallback.** If the chosen model is out of quota (429), overloaded (503), timing out or retired (404), the app tries other Gemini models. A model that just failed is skipped for a while (10 min after a quota error, 1 min after an overload), so later requests do not wait for it again. The app shows a note when a different model answered.

The free tier allows only about 20 requests per day per model, so heavy testing can use it all up; a paid key removes the limit.
Actual latency depends on Gemini: a response is typically 1–4 s when the model is healthy, but longer when the free-tier models are overloaded.
Results from fallback models (for example flash-lite) are weaker than from the Flash models and must not be compared with the paper's Gemini 3.6 Flash numbers. For paper experiments use `run_experiment.py`, which is unchanged and does not use the fallback or the English gloss.

## Requirements

- Python 3.10 or newer
- Packages in `requirements.txt` (sacreBLEU, openpyxl, google-genai, python-dotenv)
- A Gemini API key, needed only for `run_experiment.py`. Scoring and the checker work offline.

## Setup

```bash
git clone https://github.com/saungmollypolly/sociobridge-tb.git
cd sociobridge-tb
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and put your key in it:

```
GEMINI_API_KEY=your_key_here
```

`.env` is listed in `.gitignore`, so it is never uploaded.

## How to run

**1. Translate all sentences under the 5 conditions** (Zero-Shot, Full Context, No Hierarchy, No Distance, No Intent):

```bash
python src/run_experiment.py --model gemini-3.6-flash --dry-run   # preview prompts, no API calls
python src/run_experiment.py --model gemini-3.6-flash             # real run -> results/raw_outputs.jsonl
```

Each call is a fresh, stateless request (no chat history). The run is resumable: finished sentence/condition pairs are skipped.

**2. Score BLEU, chrF, chrF++ and MQM aggregates:**

```bash
python src/score.py data/pilot_outputs.json results/scores.csv
```

This regenerates every value of the pilot table below, including pooled TQ and the Check/Select row.
Each output in `data/pilot_outputs.json` stores its annotated MQM error counts per category (`errors`);
the script stops if they do not reproduce the stored sentence score.

**3. Run the rule-based politeness checker:**

```bash
python src/sociobridge_checker.py data/pilot_outputs.json data/checker_metadata.json results/
```

**4. Held-out checker test (no API key; needs the data-collection workbook):**

```bash
python src/eval_checker_heldout.py        # validated rows only (Validated = Y)
python src/eval_checker_heldout.py --all  # every row
```

## Pilot results (Gemini 3.6 Flash, 8 sentences × 5 conditions)

| Condition | Pooled MQM TQ | Mean MQM TQ | Accurate | BLEU | chrF |
|---|---|---|---|---|---|
| Zero-Shot | 0.0 | 10.0 | 0/8 | 0.18 | 13.0 |
| Full Context | 87.3 | 87.5 | 7/8 | 3.32 | 26.2 |
| No Hierarchy | 83.6 | 83.6 | 5/8 | 3.32 | 27.6 |
| No Distance | 87.3 | 88.6 | 6/8 | 3.34 | 27.6 |
| No Intent | 18.2 | 62.3 | 4/8 | 3.06 | 28.1 |
| Full Context + Check/Select | 100.0 | 100.0 | 8/8 | 3.32 | 26.9 |

Checker vs. human labels: precision 1.00, recall 0.94, F1 0.97 (TP 17, FP 0, FN 1, TN 22).

Pooled MQM TQ comes from the annotation workbook (total penalties ÷ total reference words). `score.py` reports the mean sentence TQ and the accurate count.

## Checker rules

| Rule | Check |
|---|---|
| R1 | Single translated sentence, no commentary or markdown |
| R2 | No Thai script in the Burmese output |
| R3 | No unresolved alternatives (`/`, parentheses) |
| R4 | Required polite final particle present (ခင်ဗျာ male / ရှင့် female) |
| R5 | No final particle of the wrong speaker gender |
| R6 | Address term matches the listener role |
| R7 | Self-reference fits speaker gender and hierarchy |
| R8 | No casual pronoun (ငါ, နင်) in upward speech |
| R9 | Numbers in the source are preserved (digits, Thai/Burmese digits and Burmese number words such as နှစ် = 2) |

Mapping Library coverage: **Upward** speech has full rules for male and female speakers. **Equal** and **Downward**
speech (new, not yet validated against human labels) require no polite particle and allow casual pronouns, and only
forbid self-reference of the wrong gender. When the speaker gender is **Unknown**, either gender's markers are accepted.
Address-term rules exist for Manager, Professor and Teacher; other listener roles are not checked by R6.

## Notes and limitations

- The pilot is small (8 sentences, all upward requests) and uses one free-tier model. Treat the results as preliminary.
- MQM weights are provisional, pending advisor confirmation.
- The checker rules were developed on the same pilot data, so its precision and recall are in-sample.
- The pilot metadata in `data/pilot_sentences.json` was filled in and checked against `Data_collection_File_30-Sep-2026.xlsx`. The workbook's "Validated (Y/N)" column was empty for all rows at the time of checking.
- The Decide stage, the repair step, English glosses and the Equal / Downward rules are new in the web app and are **not evaluated** in the paper's pilot. The English gloss is written by the same LLM and can be imperfect; the checker's rules, not the gloss, decide whether an output passes.
- The checker verifies politeness *form* only, not whether the Burmese reads naturally. A native speaker should still review translations.
- Never commit `.env`: it holds your API key. If a key was shared in a chat or screenshot, rotate it.
