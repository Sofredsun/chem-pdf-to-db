import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pdf_text import (
    full_text_by_column, full_text_by_page_str, extract_table_block,
    normalize_row_text, split_descriptor_and_values,
)

SOURCE_SHORT = "Kobayashi2009_BMCL"
PDF_FILENAME = "1-s2_0-S0960894X09006258-main.pdf"

LABEL_RE = re.compile(r"^\d+[a-z]?$")


def _orl1_only(block_text: str, table_ref: str) -> list:
    """
    В таблицах 1-3 пропуски hERG/logD не всегда в конце строки,
    поэтому берем только ORL1 (он всегда первый и всегда есть)
    """
    records = []
    for raw in block_text.splitlines():
        line = normalize_row_text(raw)
        tokens = line.split(" ")
        if not tokens or not LABEL_RE.match(tokens[0]):
            continue
        label = tokens[0]
        descriptor_tokens, value_tokens = split_descriptor_and_values(tokens[1:])
        if not value_tokens:
            continue
        records.append({
            "compound_label": label, "descriptor": ",".join(descriptor_tokens),
            "target_raw": "ORL1", "value_raw": value_tokens[0], "unit_raw": "nM",
            "assay_category": "binding_affinity", "assay_subtype": "IC50 (radioligand binding)",
            "table_ref": table_ref, "status": "ok", "status_note": "",
        })
    return records


def parse(pdf_path: Path) -> list:
    records = []

    cropped_text = full_text_by_column(pdf_path)
    full_text = full_text_by_page_str(pdf_path)

    records += _orl1_only(extract_table_block(cropped_text, "Table1"), "Table 1")
    records += _orl1_only(extract_table_block(full_text, "Table2"), "Table 2")
    records += _orl1_only(extract_table_block(full_text, "Table3"), "Table 3")

    # В таблице 4 каждая строка содержит все 7 свойств в конце
    block4 = extract_table_block(full_text, "Table4")
    properties4 = [
        ("ORL1", "binding_affinity", "IC50 (radioligand binding)", "nM"),
        ("ORL1", "functional_potency", "GTPgammaS antagonism IC50", "nM"),
        ("hERG", "adme", "hERG binding IC50", "nM"),
        ("physicochemical", "physicochemical", "logD7.4 (shake-flask)", "logD"),
        ("human P-gp", "adme", "transport ratio B-to-A / A-to-B (efflux)", "ratio"),
        ("physicochemical", "physicochemical", "calculated pKa, cyclopentylamine N1", "pKa"),
        ("physicochemical", "physicochemical", "calculated pKa, pyridine N2", "pKa"),
    ]
    for raw in block4.splitlines():
        line = normalize_row_text(raw)
        tokens = line.split(" ")
        if not tokens or not LABEL_RE.match(tokens[0]):
            continue
        label = tokens[0]
        descriptor_tokens, value_tokens = split_descriptor_and_values(tokens[1:])
        if len(value_tokens) != len(properties4):
            continue
        for (target, category, subtype, unit), value in zip(properties4, value_tokens):
            records.append({
                "compound_label": label, "descriptor": ",".join(descriptor_tokens),
                "target_raw": target, "value_raw": value, "unit_raw": unit,
                "assay_category": category, "assay_subtype": subtype,
                "table_ref": "Table 4", "status": "ok", "status_note": "",
            })

    # В таблице 5 берем только первые 4 токена,
    # потому что после - текст ссылок, а не данные
    block5 = extract_table_block(full_text, "Table5")
    for raw in block5.splitlines():
        line = normalize_row_text(raw)
        tokens = line.split(" ")
        if len(tokens) >= 4 and tokens[0] == "31":
            for target, value in zip(["ORL1", "MOR", "KOR"], tokens[1:4]):
                records.append({
                    "compound_label": "31", "descriptor": "", "target_raw": target,
                    "value_raw": value, "unit_raw": "nM", "assay_category": "binding_affinity",
                    "assay_subtype": "IC50/Ki (radioligand binding)", "table_ref": "Table 5",
                    "status": "ok", "status_note": "",
                })

    return records


if __name__ == "__main__":
    recs = parse(Path(__file__).parent.parent.parent / "data" / PDF_FILENAME)
    print(f"{len(recs)} records")
    by_table = {}
    for r in recs:
        by_table.setdefault(r["table_ref"], set()).add(r["compound_label"])
    for t, labels in by_table.items():
        print(t, sorted(labels, key=lambda x: (len(x), x)))
