import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pdf_text import full_text_by_page_str, extract_table_block, normalize_row_text

SOURCE_SHORT = "Fulton2008_BMCL"
PDF_FILENAME = "1-s2_0-S0960894X08008214-main.pdf"

LABEL_FIXES = {"15a": "1", "24": "2", "3a5a": "3a"}
ROW_RE = re.compile(r"^([0-9a-z]+)(?:\(([^)]+)\))?\s+(.+)$")
TARGETS = ["MOR", "DOR", "KOR"]


def parse(pdf_path: Path) -> list:
    text = full_text_by_page_str(pdf_path)
    block = extract_table_block(text, "Table1")
    records = []
    for raw in block.splitlines():
        line = normalize_row_text(raw)
        m = ROW_RE.match(line)
        if not m:
            continue
        label_raw, paren_note, rest = m.groups()
        if label_raw not in LABEL_FIXES and label_raw not in (
            "3a", "3b", "4a", "4b", "4c", "4d", "4e", "4f",
            "5a", "5b", "5c", "5d", "5e", "5f",
        ):
            continue
        label = LABEL_FIXES.get(label_raw, label_raw)
        paren_note = paren_note or ""
        tokens = rest.split(" ")
        if len(tokens) != 5:
            continue
        mu, delta, kappa, ratio, clogp = tokens
        for target, value in zip(TARGETS, (mu, delta, kappa)):
            records.append({
                "compound_label": label, "descriptor": paren_note, "target_raw": target,
                "value_raw": value, "unit_raw": "nM", "assay_category": "binding_affinity",
                "assay_subtype": "Ki (radioligand binding)", "table_ref": "Table 1",
                "status": "ok", "status_note": "",
            })
        records.append({
            "compound_label": label, "descriptor": paren_note, "target_raw": "MOR/DOR/KOR",
            "value_raw": ratio, "unit_raw": "ratio", "assay_category": "selectivity_ratio",
            "assay_subtype": "Ki ratio mu:delta:kappa (normalized)", "table_ref": "Table 1",
            "status": "ok", "status_note": "",
        })
        records.append({
            "compound_label": label, "descriptor": paren_note, "target_raw": "physicochemical",
            "value_raw": clogp, "unit_raw": "logP", "assay_category": "physicochemical",
            "assay_subtype": "CLogP (calculated)", "table_ref": "Table 1", "status": "ok", "status_note": "",
        })
    return records


if __name__ == "__main__":
    recs = parse(Path(__file__).parent.parent.parent / "data" / PDF_FILENAME)
    print(f"{len(recs)} records")
    labels = sorted({r["compound_label"] for r in recs})
    print("compounds:", labels)
