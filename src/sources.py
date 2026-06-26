import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pdf_text import PDF_DIR, extract_metadata

PDF_FILES = {
    "Yang2009_BMCL": "1-s2.0-S0960894X09003679-main.pdf",
    "Pettersson2009_JMC": "synthesis-and-evaluation-of-dibenzothiazepines-a-novel-class-of-selective-cannabinoid-1-receptor-inverse-agonists.pdf",
    "Guerrini2009_JMC": "further-studies-at-neuropeptide-s-position-5-discovery-of-novel-neuropeptide-s-receptor-antagonists.pdf",
    "Li2009_JMC": "design-synthesis-and-biological-evaluation-of-6α-and-6β-n-heterocyclic-substituted-naltrexamine-derivatives-as-μ-opioid.pdf",
    "Iyer2012_EJMC": "1-s2.0-S0223523412000402-main.pdf",
    "Kobayashi2009_BMCL": "1-s2.0-S0960894X09006258-main.pdf",
    "Dolle2009_BMCL": "1-s2.0-S0960894X09006222-main.pdf",
    "Fulton2008_BMCL": "1-s2.0-S0960894X08008214-main.pdf",
}

# Есть в пдф растровые картинки.
# OCR не реализован. Данных из этих таблиц в базе нет.
KNOWN_IMAGE_TABLES = {
    "Pettersson2009_JMC": ["Table 1 (R-SAT/binding/Clint SAR table)"],
    "Guerrini2009_JMC": ["Table 1 (NPS [D-Xaa5] analogue SAR table)"],
}


def sources_with_metadata() -> list:
    out = []
    for short, fname in PDF_FILES.items():
        meta = extract_metadata(PDF_DIR / fname)
        out.append({
            "source_short": short,
            "pdf_filename": fname,
            "journal": meta["journal"],
            "year": meta["year"],
            "volume": meta["volume"],
            "pages": meta["pages"],
            "doi": meta["doi"],
            "title": meta["title"],
            "image_table_caveat": "; ".join(KNOWN_IMAGE_TABLES.get(short, [])),
        })
    return out
