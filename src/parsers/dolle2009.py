import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pdf_text import full_text_by_column, extract_table_block, normalize_row_text

SOURCE_SHORT = "Dolle2009_BMCL"
PDF_FILENAME = "1-s2_0-S0960894X09006222-main.pdf"

LABEL_RE = re.compile(r"^\d+$")
CODE_MAP = {"c": ">1000", "e": "nd"}
COLUMNS = ["KOR", "MOR", "DOR", "MOR/KOR_ratio", "KOR_IC50", "MOR_IC50"]


def parse(pdf_path: Path) -> list:
    text = full_text_by_column(pdf_path)
    block = extract_table_block(text, "Table1")
    records = []
    for raw in block.splitlines():
        line = normalize_row_text(raw)
        tokens = line.split(" ")
        if len(tokens) != 7 or not LABEL_RE.match(tokens[0]):
            continue
        label = tokens[0]
        values = [CODE_MAP.get(t, t) for t in tokens[1:7]]
        kor, mor, dor, ratio, kor_ic50, mor_ic50 = values

        for target, value in (("KOR", kor), ("MOR", mor), ("DOR", dor)):
            records.append({
                "compound_label": label, "descriptor": "", "target_raw": target,
                "value_raw": value, "unit_raw": "nM", "assay_category": "binding_affinity",
                "assay_subtype": "Ki (radioligand binding)", "table_ref": "Table 1",
                "status": "ok", "status_note": "",
            })
        if ratio not in ("\u2014", "-", "nd"):
            records.append({
                "compound_label": label, "descriptor": "", "target_raw": "MOR/KOR",
                "value_raw": ratio, "unit_raw": "ratio", "assay_category": "selectivity_ratio",
                "assay_subtype": "Ki(MOR)/Ki(KOR)", "table_ref": "Table 1", "status": "ok", "status_note": "",
            })
        for target, value in (("KOR", kor_ic50), ("MOR", mor_ic50)):
            records.append({
                "compound_label": label, "descriptor": "", "target_raw": target,
                "value_raw": value, "unit_raw": "nM", "assay_category": "functional_potency",
                "assay_subtype": "35S-GTPgammaS antagonist IC50", "table_ref": "Table 1",
                "status": "ok", "status_note": "",
            })
    return records


if __name__ == "__main__":
    recs = parse(Path(__file__).parent.parent.parent / "data" / PDF_FILENAME)
    print(f"{len(recs)} records")
    labels = sorted({r["compound_label"] for r in recs}, key=int)
    print("compounds:", labels)
