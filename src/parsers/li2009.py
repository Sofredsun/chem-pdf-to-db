import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pdf_text import find_caption_position, extract_rows_by_position, normalize_row_text

SOURCE_SHORT = "Li2009_JMC"
PDF_FILENAME = "design-synthesis-and-biological-evaluation-of-6α-and-6β-n-heterocyclic-substituted-naltrexamine-derivatives-as-μ-opioid.pdf"

LABEL_RE = re.compile(r"^([A-Za-z0-9.\-]+?)(\([A-Z]+\))?$")
PLUS_MINUS_FIX_RE = re.compile(r"(?<=\d)\((?=\d)")


def _fix_pm(line: str) -> str:
    """В PDF символ ± выходит как обычная скобка '(' между цифрами"""
    return PLUS_MINUS_FIX_RE.sub("\u00b1", line)


def _rows_between(pdf_path, start_label, end_label, x_range):
    start = find_caption_position(pdf_path, start_label)
    if start is None:
        return []
    page_num, x0, top = start
    end = find_caption_position(pdf_path, end_label) if end_label else None
    if end and end[0] == page_num:
        bottom = end[2]
    else:
        bottom = top + 420
    return extract_rows_by_position(pdf_path, page_num, x_range=x_range, y_range=(top, bottom))


def parse(pdf_path: Path) -> list:
    records = []

    # Таблица 2: Ki у MOR/DOR/KOR + коэффициенты селективности
    pos2 = find_caption_position(pdf_path, "Table2")
    x0 = pos2[1] if pos2 else 50
    lines = _rows_between(pdf_path, "Table2", "Table3", x_range=(x0 - 30, x0 + 490))
    targets2 = ["MOR", "DOR", "KOR"]
    for raw in lines:
        line = _fix_pm(normalize_row_text(raw))
        tokens = line.split(" ")
        if len(tokens) != 6:
            continue
        label = tokens[0]
        # Шрифт PDF рисует β и ± одним и тем же глифом,
        # поэтому 'β-FNA' извлекается как '±-FNA
        if label == "\u00b1-FNA":
            label = "beta-FNA"
        if not re.match(r"^[A-Za-z0-9.\-]+(\([A-Z]+\))?$", label) or label.lower() in ("compd",):
            continue
        values = tokens[1:4]
        ratios = tokens[4:6]
        if not all(re.match(r"^[\d.]+\u00b1?[\d.]*$", v) for v in values):
            continue
        for target, value in zip(targets2, values):
            records.append({
                "compound_label": label, "descriptor": "", "target_raw": target,
                "value_raw": value, "unit_raw": "nM", "assay_category": "binding_affinity",
                "assay_subtype": "Ki (radioligand binding)", "table_ref": "Table 2",
                "status": "ok", "status_note": "",
            })
        records.append({
            "compound_label": label, "descriptor": "", "target_raw": "DOR/MOR",
            "value_raw": ratios[0], "unit_raw": "ratio", "assay_category": "selectivity_ratio",
            "assay_subtype": "Ki(DOR)/Ki(MOR)", "table_ref": "Table 2", "status": "ok", "status_note": "",
        })
        records.append({
            "compound_label": label, "descriptor": "", "target_raw": "KOR/MOR",
            "value_raw": ratios[1], "unit_raw": "ratio", "assay_category": "selectivity_ratio",
            "assay_subtype": "Ki(KOR)/Ki(MOR)", "table_ref": "Table 2", "status": "ok", "status_note": "",
        })

    pos3 = find_caption_position(pdf_path, "Table3")
    x0_3 = pos3[1] if pos3 else 50
    lines3 = _rows_between(pdf_path, "Table3", "Table4", x_range=(x0_3 - 30, x0_3 + 380))
    for raw in lines3:
        line = _fix_pm(normalize_row_text(raw))
        tokens = line.split(" ")
        if len(tokens) != 4:
            continue
        label = tokens[0]
        if not re.match(r"^[A-Za-z0-9.\-]+(\([A-Z]+\))?$", label) or label.lower() == "compd":
            continue
        ec50, emax, pctmax = tokens[1:4]
        if not re.match(r"^[\d.]+\u00b1[\d.]+$", ec50):
            continue
        records.append({
            "compound_label": label, "descriptor": "", "target_raw": "MOR",
            "value_raw": ec50, "unit_raw": "nM", "assay_category": "functional_potency",
            "assay_subtype": "35S-GTPgammaS EC50", "table_ref": "Table 3", "status": "ok", "status_note": "",
        })
        records.append({
            "compound_label": label, "descriptor": "", "target_raw": "MOR",
            "value_raw": emax, "unit_raw": "%stim", "assay_category": "functional_potency",
            "assay_subtype": "35S-GTPgammaS Emax", "table_ref": "Table 3", "status": "ok", "status_note": "",
        })
        records.append({
            "compound_label": label, "descriptor": "", "target_raw": "MOR",
            "value_raw": pctmax, "unit_raw": "%", "assay_category": "functional_potency",
            "assay_subtype": "% of DAMGO maximal stimulation", "table_ref": "Table 3", "status": "ok", "status_note": "",
        })

    return records


if __name__ == "__main__":
    recs = parse(Path(__file__).parent.parent.parent / "data" / PDF_FILENAME)
    print(f"{len(recs)} records")
    seen = set()
    for r in recs:
        key = r["compound_label"]
        if key not in seen:
            seen.add(key)
    print("compounds seen:", sorted(seen))
