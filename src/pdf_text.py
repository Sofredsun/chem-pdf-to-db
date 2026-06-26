import re
from pathlib import Path

import pdfplumber

PDF_DIR = Path(__file__).parent.parent / "data"


def column_texts(pdf_path: Path):
    """
    Текст по частям: один кусок на (страницу, колонку), в порядке чтения.
    Большинство страниц двухколоночные
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            x0, y0, x1, y1 = page.bbox
            mid = (x0 + x1) / 2
            left = page.crop((x0, y0, mid, y1)).extract_text() or ""
            right = page.crop((mid, y0, x1, y1)).extract_text() or ""
            yield left
            yield right


def full_text_by_page(pdf_path: Path):
    """
    Текст по страницам, без обрезки. Двухколоночный основной текст и
    любая пара узких таблиц, стоящих рядом на одной странице, будут искажены
    этим способом. Но таблица, которая занимает всю ширину страницы
    наоборот: обрезка пополам отрежет часть колонок, поэтому ей
    нужен именно текст без обрезки. Каждый парсер конкретной статьи сам
    выбирает, какой режим подходит для конкретной таблицы.
    """
    with pdfplumber.open(pdf_path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def full_text_by_page_str(pdf_path: Path) -> str:
    """
    Тот же формат склейки кусков через разделитель, что и в
    full_text_by_column(), но один кусок на страницу (без обрезки),
    а не один кусок на половину страницы.
    """
    return "\n<<<COLBREAK>>>\n".join(full_text_by_page(pdf_path))


def full_text_by_column(pdf_path: Path) -> str:
    """
    Все чанки-колонки склеены через разделитель, для поиска заголовков.
    """
    return "\n<<<COLBREAK>>>\n".join(column_texts(pdf_path))


def extract_table_block(full_text: str, table_label: str, stop_labels=None) -> str:
    """
    Возвращает исходный текст между строкой-заголовком "Table N" / "Table N."
    и следующим заголовком таблицы / явной стоп-меткой, просматривая чанки
    колонок по порядку.
    """
    heading_re = re.compile(r"^" + re.escape(table_label) + r"(\.|\s|$)")
    chunks = full_text.split("\n<<<COLBREAK>>>\n")
    stop_re = re.compile(
        r"^(Table\d+|Scheme\d+|Figure\d+" +
        "".join(f"|{re.escape(s)}" for s in (stop_labels or [])) +
        r")",
    )
    for chunk in chunks:
        lines = chunk.splitlines()
        heading_idx = next((i for i, l in enumerate(lines) if heading_re.match(l.strip())), None)
        if heading_idx is None:
            continue
        heading_line = lines[heading_idx].strip()
        # Если текст подписи идет сразу на строке заголовка,
        # убираем только префикс "TableN." и оставляем остальное как
        # первую строку блока.
        rest_of_heading = heading_re.sub("", heading_line, count=1).strip()
        out = [rest_of_heading] if rest_of_heading else []
        for line in lines[heading_idx + 1:]:
            if stop_re.match(line.strip()):
                break
            out.append(line)
        return "\n".join(out)
    return ""


VALUE_TOKEN_RE = re.compile(
    r"^(>|<)?\d[\d,]*(\.\d+)?(\u00b1\d+(\.\d+)?)?$|^nd$|^na$|^inactive$",
    re.IGNORECASE,
)


def split_descriptor_and_values(tokens):
    """
    tokens: содержимое строки после разбиения по пробелам, после
    ведущей метки соединения. Сканирует справа налево серию токенов,
    "похожих на значение" (обычные числа, >N/<N, nd/na/inactive), и
    возвращает (descriptor_tokens, value_tokens).
    """
    i = len(tokens)
    while i > 0 and VALUE_TOKEN_RE.match(tokens[i - 1]):
        i -= 1
    return tokens[:i], tokens[i:]


HEADER_TARGET_RE = re.compile(r"(?:^|\s)([A-Za-z]{2,6})\s*Ki\s*\(nM\)", re.IGNORECASE)


def targets_from_header(header_line: str):
    """
    Читает собственную строку-заголовок таблицы (например,
    'Compds R NOPKi(nM) MOPKi(nM)') и возвращает названия целей в порядке
    колонок (например, ['NOP', 'MOP']), вместо того чтобы жестко прописывать,
    какой рецептор означает каждая колонка значений.
    """
    return [m.group(1).upper() for m in HEADER_TARGET_RE.finditer(header_line)]


def parse_simple_ki_table(block_text: str, label_pattern=r"^\d+[a-z]?$"):
    """
    Парсит блок таблицы вида 'Compds <колонки-дескрипторы...>
    <Target>Ki(nM) ...' (именно такой формат используется в 4 из 8 статей)
    в список словарей: {"label": ..., "descriptor": "...", "values": {target: raw_str}}.
    """
    lines = [normalize_row_text(l) for l in block_text.splitlines()]
    lines = [l for l in lines if l]

    header_line = next((l for l in lines if "Ki(nM)" in l.replace(" ", "")), "")
    targets = targets_from_header(header_line)
    if not targets:
        return []

    label_re = re.compile(label_pattern)
    rows = []
    for line in lines:
        tokens = line.split(" ")
        if not tokens or not label_re.match(tokens[0]):
            continue
        label, rest = tokens[0], tokens[1:]
        descriptor_tokens, value_tokens = split_descriptor_and_values(rest)
        if len(value_tokens) != len(targets):
            continue
        rows.append({
            "label": label,
            "descriptor": ",".join(descriptor_tokens),
            "values": dict(zip(targets, value_tokens)),
        })
    return rows


def extract_rows_by_position(pdf_path: Path, page_num: int, x_range=None, y_range=None, y_tolerance=3):
    """
    Извлекает слова в пределах прямоугольной области на одной странице,
    группирует их в строки по вертикальной позиции и возвращает слова
    каждой строки, отсортированные слева направо, то есть восстанавливает
    каждую строку именно так, как она расположена на странице, независимо
    от порядка, который иначе дал бы дефолтный построчный алгоритм
    pdfplumber. Это обходит два режима сбоев, встречающихся у обычного
    extract_text():
      - две стоящие рядом таблицы/колонки на одной высоте склеиваются в
        одну искаженную строку, и
      - таблица, "плавающая" посреди обычного текста, оказывается со
        своими строками раскиданными по окружающему абзацу.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        words = page.extract_words()

    if x_range:
        words = [w for w in words if x_range[0] <= w["x0"] <= x_range[1]]
    if y_range:
        words = [w for w in words if y_range[0] <= w["top"] <= y_range[1]]

    words = sorted(words, key=lambda w: w["top"])
    clusters = []
    for w in words:
        if clusters and w["top"] - clusters[-1][-1]["top"] <= y_tolerance:
            clusters[-1].append(w)
        else:
            clusters.append([w])

    lines = []
    for cluster in clusters:
        row_words = sorted(cluster, key=lambda w: w["x0"])
        lines.append(" ".join(rw["text"] for rw in row_words))
    return lines


def find_caption_position(pdf_path: Path, table_label: str):
    """
    Находит заголовок "TableN" по его реальной позиции (страница, x, y)
    (а не просто текстовым поиском), чтобы вызывающий код мог вывести
    y_range для extract_rows_by_position без ручного указания координат.
    """
    heading_re = re.compile(r"^" + re.escape(table_label) + r"(\.|$)")
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            for w in words:
                if heading_re.match(w["text"]):
                    return page_num, w["x0"], w["top"]
    return None


def normalize_row_text(line: str) -> str:
    """
    Убирает странные артефакты лигатур/пробелов, которые иногда
    оставляет pdfplumber, не трогая сами данные в токенах.
    """
    line = line.replace("\xa0", " ")
    line = re.sub(r"\(cid:\d+\)", "\u00b1", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line

_KNOWN_JOURNAL_NAMES = {
    "Bioorganic & Medicinal Chemistry Letters",
    "Journal of Medicinal Chemistry",
    "European Journal of Medicinal Chemistry",
}

DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s,;]+")
MASTHEAD_RE_ELSEVIER = re.compile(
    r"([A-Za-z&.\s]+?)\s*(\d{1,4})\s*\((\d{4})\)\s*(\d+)[\u2013\-e](\d+)"
)
MASTHEAD_RE_ACS = re.compile(
    r"([A-Za-z.\s]+?)\.?\s*(\d{4}),\s*(\d+),\s*(\d+)[\u2013\-e](\d+)"
)


def extract_metadata(pdf_path: Path) -> dict:
    """
    Достает журнал, год, том, страницы, DOI и название прямо со страницы 1
    Если чего-то нет, то оставляет пустую строку, а не угадывает.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        words = page.extract_words(extra_attrs=["size"])

    meta = {"journal": "", "year": "", "volume": "", "pages": "", "doi": "", "title": ""}
    flat = text.replace("\n", " ")

    m = MASTHEAD_RE_ELSEVIER.search(flat)
    if m:
        meta["journal"] = re.sub(r"\s+", " ", m.group(1)).strip()
        meta["volume"] = m.group(2)
        meta["year"] = m.group(3)
        meta["pages"] = f"{m.group(4)}-{m.group(5)}"
    else:
        m = MASTHEAD_RE_ACS.search(flat.strip())
        if m:
            meta["journal"] = re.sub(r"\s+", " ", m.group(1)).strip()
            meta["year"] = m.group(2)
            meta["volume"] = m.group(3)
            meta["pages"] = f"{m.group(4)}-{m.group(5)}"

    doi_m = DOI_RE.search(text)
    if doi_m:
        meta["doi"] = doi_m.group(0).split("CCC")[0].rstrip(".")

    if words:
        sizes_present = sorted({round(w["size"], 1) for w in words}, reverse=True)
        for size in sizes_present:
            line = " ".join(w["text"] for w in words if round(w["size"], 1) == size)
            line_clean = re.sub(r"\s+", " ", line).strip()
            if line_clean in _KNOWN_JOURNAL_NAMES:
                continue
            if len(line_clean.split()) >= 4:
                meta["title"] = line_clean
                break

    return meta
