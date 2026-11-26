"""Load sentences from the data-collection workbook into the app's sentence format."""
from pathlib import Path

import openpyxl

DEFAULT_PATH = (Path(__file__).resolve().parent.parent.parent
                / "Data collection metadata file" / "Data_collection_File_30-Sep-2026.xlsx")

FIX = {"Unfamilar": "Unfamiliar", "Same Age": "Same", "Students": "Student"}


def _n(v, default="Unknown"):
    v = str(v).strip() if v is not None else ""
    return FIX.get(v, v) or default


def load_workbook_sentences(path=DEFAULT_PATH):
    """Return a list of sentence dicts for every row with the core fields filled.
    `validated` records the workbook's Validated (Y/N) value ('' when blank)."""
    path = Path(path)
    if not path.exists():
        return []
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    for r in list(wb["Dataset Collection"].iter_rows(values_only=True))[1:]:
        r = list(r) + [None] * 23
        if not (r[0] and r[4] and r[3] and r[12] and r[9] and r[10]):
            continue
        out.append({
            "no": r[0], "setting": _n(r[3]), "th": str(r[4]).strip(),
            "en": _n(r[5], ""), "ref_my": _n(r[6], ""),
            "speaker": {"role": _n(r[9]), "gender": _n(r[7])},
            "listener": {"role": _n(r[10]), "gender": _n(r[8])},
            "social_hierarchy": {"direction": _n(r[12]), "relative_age": _n(r[15]),
                                 "relative_status": _n(r[16])},
            "social_distance": _n(r[14], "Familiar"),
            "communicative_intent": _n(r[17], "Information"),
            "validated": _n(r[21], ""),
        })
    return out
