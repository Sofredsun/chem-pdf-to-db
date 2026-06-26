import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pdf_text import full_text_by_column, extract_table_block, parse_simple_ki_table

SOURCE_SHORT = "Yang2009_BMCL"
PDF_FILENAME = "1-s2_0-S0960894X09003679-main.pdf"

# Все таблицы статьи имеют одинаковый формат,
# поэтому используется общий parse_simple_ki_table
TABLE_LABELS = ["Table1", "Table2", "Table3", "Table4", "Table5"]


def parse(pdf_path: Path) -> list:
    """
    Возвращает список словарей исходных измерений:
    {compound_label, descriptor, target_raw, value_raw, table_ref}
    """
    full_text = full_text_by_column(pdf_path)
    records = []
    for table_label in TABLE_LABELS:
        block = extract_table_block(full_text, table_label)
        if not block.strip():
            continue
        rows = parse_simple_ki_table(block)
        for row in rows:
            for target, value in row["values"].items():
                records.append({
                    "compound_label": row["label"],
                    "descriptor": row["descriptor"],
                    "target_raw": target,
                    "value_raw": value,
                    "unit_raw": "nM",
                    "assay_category": "binding_affinity",
                    "assay_subtype": "Ki (radioligand binding)",
                    "table_ref": table_label.replace("Table", "Table "),
                })
    return records


if __name__ == "__main__":
    recs = parse(Path(__file__).parent.parent.parent / "data" / PDF_FILENAME)
    print(f"{len(recs)} records extracted")
    for r in recs[:12]:
        print(r)
