"""
Пайплайн: код читает PDF -> стандартизирует/очищает ->
пишет одну CSV-таблицу.

Шаги:
  1. Вызывается каждый src/parsers/<paper>.py:parse(pdf_path), который
     открывает настоящий PDF (pdfplumber) и извлекает номера соединений
     и значения активности из текста таблицы.
  2. Стандартизируются названия рецепторов и единицы измерения.
  3. Обнаруживаются точные дубликаты измерений (сливаются в одну
     запись) и настоящие конфликты (помечаются оба, оба сохраняются).
  4. Делается попытка подобрать SMILES через PubChem для соединений,
     у которых извлеченный из PDF descriptor - настоящее химическое
     или торговое название (src/enrich_smiles.py).
  5. Все объединяется (источник + описание соединения + измерение)
     в одну таблицу: data/database.csv.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pdf_text import PDF_DIR
from sources import sources_with_metadata, PDF_FILES, KNOWN_IMAGE_TABLES
from enrich_smiles import enrich_compounds_with_smiles
from parsers import yang2009, li2009, iyer2012, dolle2009, fulton2008, kobayashi2009

OUT_DIR = Path(__file__).parent.parent / "data"
OUT_DIR.mkdir(exist_ok=True)

PARSERS = {
    "Yang2009_BMCL": yang2009,
    "Li2009_JMC": li2009,
    "Iyer2012_EJMC": iyer2012,
    "Dolle2009_BMCL": dolle2009,
    "Fulton2008_BMCL": fulton2008,
    "Kobayashi2009_BMCL": kobayashi2009,
    # Pettersson2009_JMC, Guerrini2009_JMC: таблица в PDF является
    # растровой картинкой, а не текстом.
    # Парсер (OCR) для них не написан, к сожалению.
}

# Стандартизация названий
TARGET_STD_MAP = {
    "NOP": "NOP", "ORL1": "NOP",
    "MOP": "MOR", "MOR": "MOR",
    "DOP": "DOR", "DOR": "DOR",
    "KOP": "KOR", "KOR": "KOR",
    "CB1": "CB1", "CB2": "CB2",
    "hERG": "hERG",
}


def standardize_target(raw):
    raw = (raw or "").strip()
    if raw in TARGET_STD_MAP:
        return TARGET_STD_MAP[raw]
    for sep in ("/",):
        if sep in raw and all(tok.strip() in TARGET_STD_MAP for tok in raw.split(sep)):
            return sep.join(TARGET_STD_MAP[tok.strip()] for tok in raw.split(sep))
    return raw


NUMERIC_LEAD_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)")


def parse_value(raw, unit_raw):
    if raw is None or raw == "":
        return None, unit_raw, "not_determined" if raw == "" else "", ""
    text = str(raw).strip()
    low = text.lower()

    if low == "nd":
        return None, unit_raw, "not_determined", "Reported as 'nd' in the source paper."
    if low == "na":
        return None, unit_raw, "not_active", "Reported as 'na' (not active) in the source paper."

    censor = ""
    work = text
    if work.startswith(">"):
        censor, work = "above", work[1:]
    elif work.startswith("<"):
        censor, work = "below", work[1:]

    # Пропуск ±SEM для числа
    work_for_match = work.split("\u00b1")[0]
    m = NUMERIC_LEAD_RE.match(work_for_match.replace(",", ""))
    if not m:
        return None, unit_raw, "non_numeric", f"Value is non-numeric/composite ('{text}') -- see value_raw."

    value = float(m.group(1))
    note = ""
    if censor == "above":
        note = f"Source paper reports only a lower bound ('{text}'); true value is greater than {value} {unit_raw}."
    elif censor == "below":
        note = f"Source paper reports only an upper bound ('{text}'); true value is less than {value} {unit_raw}."
    return value, unit_raw, censor, note


# Шаг 1: запуск каждого парсера
raw_rows = []
parse_errors = []
for source_short, module in PARSERS.items():
    pdf_path = PDF_DIR / PDF_FILES[source_short]
    try:
        records = module.parse(pdf_path)
    except Exception as e:
        parse_errors.append((source_short, str(e)))
        records = []
    for r in records:
        r["source_short"] = source_short
        raw_rows.append(r)

# Шаг 2: очистка
clean_rows = []
for i, r in enumerate(raw_rows, start=1):
    target_std = standardize_target(r["target_raw"])
    status = r.get("status", "ok")
    if status == "needs_review":
        value_std, unit_std, censor, note = None, r.get("unit_raw", ""), "needs_review", r.get("status_note", "")
    else:
        value_std, unit_std, censor, note = parse_value(r["value_raw"], r["unit_raw"])

    clean_rows.append({
        "measurement_id": i,
        "compound_id": f"{r['source_short']}__{r['compound_label']}",
        "source_short": r["source_short"],
        "compound_label": r["compound_label"],
        "descriptor": r.get("descriptor", ""),
        "target_raw": r["target_raw"],
        "target_std": target_std,
        "assay_category": r["assay_category"],
        "assay_subtype": r["assay_subtype"],
        "value_raw": r["value_raw"],
        "unit_raw": r["unit_raw"],
        "value_std": "" if value_std is None else round(value_std, 6),
        "unit_std": unit_std,
        "censor": censor,
        "table_ref": r["table_ref"],
        "note": note,
        "conflict_flag": "",
    })

# Шаг 3: мерж дубликатов и пометка конфликтов
groups = defaultdict(list)
for row in clean_rows:
    if row["value_std"] != "":
        key = (row["compound_id"], row["target_std"], row["assay_subtype"])
        groups[key].append(row)

rows_to_drop = set()
duplicate_merge_count = 0
conflict_count = 0
for key, rows in groups.items():
    if len(rows) <= 1:
        continue
    values = {r["value_std"] for r in rows}
    if len(values) == 1:
        duplicate_merge_count += 1
        keep, drop = rows[0], rows[1:]
        keep["table_ref"] = " ; ".join(sorted({r["table_ref"] for r in rows}))
        keep["note"] = " | ".join(p for p in [keep["note"], f"Exact duplicate in {len(rows)} locations; merged."] if p)
        rows_to_drop.update(d["measurement_id"] for d in drop)
    else:
        conflict_count += 1
        ids = ", ".join(f"#{r['measurement_id']}={r['value_std']}" for r in rows)
        for r in rows:
            r["conflict_flag"] = f"CONFLICT with {len(rows)-1} other record(s): {ids}"

clean_rows = [r for r in clean_rows if r["measurement_id"] not in rows_to_drop]

# Шаг 4: SMILES обогощение соединений
compounds_by_id = {}
for r in clean_rows:
    compounds_by_id.setdefault(r["compound_id"], {
        "compound_id": r["compound_id"], "source_short": r["source_short"],
        "compound_label": r["compound_label"], "descriptor": r["descriptor"],
        "smiles": "", "smiles_source": "", "smiles_note": "",
    })

SOURCES_WITH_REAL_NAME_DESCRIPTORS = {"Fulton2008_BMCL"}
LABEL_TO_COMMON_NAME = {
    "NTX": "naltrexone", "beta-FNA": "beta-funaltrexamine",
    "CTAP": "CTAP", "DAMGO": "DAMGO",
}
NOT_A_REAL_NAME_RE = re.compile(r"^(MCL-\d+|NAP|NAQ)$", re.IGNORECASE)

lookup_names = {}
for cid, c in compounds_by_id.items():
    label = c["compound_label"]
    desc = c["descriptor"].strip()
    if label in LABEL_TO_COMMON_NAME:
        lookup_names[cid] = LABEL_TO_COMMON_NAME[label]
    elif (
        c["source_short"] in SOURCES_WITH_REAL_NAME_DESCRIPTORS
        and desc and not NOT_A_REAL_NAME_RE.match(desc) and not re.match(r"^[\d.,]+$", desc)
    ):
        lookup_names[cid] = desc

n_attempted, n_found = enrich_compounds_with_smiles(list(compounds_by_id.values()), lookup_names)

# Шаг 5: соединение в одну таблицу
sources_by_short = {s["source_short"]: s for s in sources_with_metadata()}

DATABASE_FIELDS = [
    "measurement_id", "compound_id", "compound_label", "descriptor",
    "smiles", "smiles_source", "smiles_note",
    "source_short", "source_journal", "source_year", "source_doi", "source_title",
    "target_raw", "target_std", "assay_category", "assay_subtype",
    "value_raw", "unit_raw", "value_std", "unit_std", "censor",
    "table_ref", "note", "conflict_flag",
]

database_rows = []
for r in clean_rows:
    compound = compounds_by_id.get(r["compound_id"], {})
    source = sources_by_short.get(r["source_short"], {})
    database_rows.append({
        "measurement_id": r["measurement_id"],
        "compound_id": r["compound_id"],
        "compound_label": r["compound_label"],
        "descriptor": r["descriptor"],
        "smiles": compound.get("smiles", ""),
        "smiles_source": compound.get("smiles_source", ""),
        "smiles_note": compound.get("smiles_note", ""),
        "source_short": r["source_short"],
        "source_journal": source.get("journal", ""),
        "source_year": source.get("year", ""),
        "source_doi": source.get("doi", ""),
        "source_title": source.get("title", ""),
        "target_raw": r["target_raw"],
        "target_std": r["target_std"],
        "assay_category": r["assay_category"],
        "assay_subtype": r["assay_subtype"],
        "value_raw": r["value_raw"],
        "unit_raw": r["unit_raw"],
        "value_std": r["value_std"],
        "unit_std": r["unit_std"],
        "censor": r["censor"],
        "table_ref": r["table_ref"],
        "note": r["note"],
        "conflict_flag": r["conflict_flag"],
    })

DATABASE_PATH = OUT_DIR / "database.csv"
with open(DATABASE_PATH, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=DATABASE_FIELDS)
    w.writeheader()
    w.writerows(database_rows)

for stale in ("sources.csv", "compounds.csv", "measurements.csv"):
    p = OUT_DIR / stale
    if p.exists():
        p.unlink()
