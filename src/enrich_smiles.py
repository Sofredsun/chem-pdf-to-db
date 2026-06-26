"""
Подбор SMILES с PubChem для соединений,
у которых модели не извлекли структуру из PDF.

Шаги:
  1. Для каждого соединения смотрим LOOKUP_NAMES - формируется в
     src/build_database.py из поля descriptor, которое извлек парсер,
     и небольшого словаря известных референсных названий.
  2. Если название есть — пробуем PubChem PUG REST:
     GET /compound/name/{name}/property/CanonicalSMILES/TXT
  3. Если названия нет, запрос не удался или PubChem ничего не нашел,
     то SMILES остается пустым, а `smiles_note` объясняет, почему именно
     (без сети / нет совпадения / название не присвоено вовсе).
"""
import json
import time
from pathlib import Path
from urllib.parse import quote

try:
    import requests
    _REQUESTS_AVAILABLE = True
# Пайплайн не должен падать, если requests не установлен
except ImportError:
    requests = None
    _REQUESTS_AVAILABLE = False

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
HEADERS = {"User-Agent": "Mozilla/5.0 (chem-sar-extraction-pipeline; student project)"}
CACHE_PATH = Path(__file__).parent / ".smiles_cache.json"
RATE_LIMIT_SECONDS = 0.34


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_smiles_by_name(name: str, cache: dict | None = None, timeout: int = 20) -> str | None:
    """
    Возвращает Canonical SMILES с PubChem по точному названию, либо None.

    Кэш (.smiles_cache.json, рядом с этим файлом) экономит запросы при
    повторных прогонах build_database.py — это служебный файл, а не часть
    БД, и в data/ не попадает (см. .gitignore).
    """
    if not name:
        return None
    if cache is not None and name in cache:
        return cache[name] or None
    if not _REQUESTS_AVAILABLE:
        return None

    url = f"{PUBCHEM_BASE}/compound/name/{quote(name, safe='')}/property/CanonicalSMILES/TXT"
    smiles = None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 200:
            lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
            smiles = lines[0] if lines else None
    except requests.RequestException:
        smiles = None

    if cache is not None:
        cache[name] = smiles
    time.sleep(RATE_LIMIT_SECONDS)
    return smiles


def enrich_compounds_with_smiles(compounds: list, lookup_names: dict) -> tuple[int, int]:
    """
    Мутирует список compounds на месте, заполняя smiles/smiles_source/
    smiles_note. Возвращает (сколько имен пробовали, сколько нашли) —
    было использовано для логирования.
    """
    cache = _load_cache()
    n_attempted = 0
    n_found = 0
    try:
        for c in compounds:
            name = lookup_names.get(c["compound_id"])
            if not name:
                c["smiles_note"] = (
                    "В статье структура дана только как 2D-картинка / запись в "
                    "таблице R-групп — однозначного названия для поиска нет "
                    "(см. README, 'Известные ограничения')."
                )
                continue

            n_attempted += 1
            smiles = fetch_smiles_by_name(name, cache=cache)
            if smiles:
                n_found += 1
                c["smiles"] = smiles
                c["smiles_source"] = f"pubchem:name={name!r}"
                c["smiles_note"] = ""
            else:
                c["smiles_note"] = (
                    f"Искали на PubChem по названию {name!r}, но не нашли (либо "
                    f"сеть недоступна — перезапустите build_database.py с интернетом)."
                )
    finally:
        _save_cache(cache)

    return n_attempted, n_found
