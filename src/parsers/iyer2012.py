import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pdf_text import (
    find_caption_position, extract_rows_by_position,
    normalize_row_text, split_descriptor_and_values,
)

SOURCE_SHORT = "Iyer2012_EJMC"
PDF_FILENAME = "1-s2_0-S0223523412000402-main.pdf"

LABEL_RE = re.compile(r"^([0-9]+[a-z]?)(\[\d+\])?$")
TARGETS = ["MOR", "DOR", "KOR"]


def parse(pdf_path: Path) -> list:
    pos = find_caption_position(pdf_path, "Table2")
    if pos is None:
        return []
    page_num, x0, top = pos

    lines = extract_rows_by_position(
        pdf_path, page_num, x_range=(x0 - 5, x0 + 220), y_range=(top, top + 300),
    )

    records = []
    for raw in lines:
        line = normalize_row_text(raw)
        tokens = line.split(" ")
        if not tokens:
            continue
        m = LABEL_RE.match(tokens[0])
        if not m:
            continue
        label = m.group(1)
        descriptor_tokens, value_tokens = split_descriptor_and_values(tokens[1:])

        if descriptor_tokens or len(value_tokens) != len(TARGETS):
            # При неудаче разделения делаем отметку на ручную проверку
            records.append({
                "compound_label": label,
                "descriptor": "",
                "target_raw": "/".join(TARGETS),
                "value_raw": "",
                "unit_raw": "nM",
                "assay_category": "binding_affinity",
                "assay_subtype": "Ki (radioligand binding)",
                "table_ref": "Table 2",
                "status": "needs_review",
                "status_note": f"Row text didn't split cleanly into label + {len(TARGETS)} values: {raw!r}",
            })
            continue

        for target, value in zip(TARGETS, value_tokens):
            records.append({
                "compound_label": label,
                "descriptor": "",
                "target_raw": target,
                "value_raw": value,
                "unit_raw": "nM",
                "assay_category": "binding_affinity",
                "assay_subtype": "Ki (radioligand binding)",
                "table_ref": "Table 2",
                "status": "ok",
                "status_note": "",
            })
    return records


if __name__ == "__main__":
    recs = parse(Path(__file__).parent.parent.parent / "data" / PDF_FILENAME)
    print(f"{len(recs)} records")
    for r in recs:
        print(r["compound_label"], r["target_raw"], r["value_raw"], r["status"])
