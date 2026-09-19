"""Dependency-free Italian cardinal number parser.

Supports 0-999_999 in their standard written form (e.g. ``centottanta``,
``duecentoquaranta``, ``millecinquecento``, ``duemilatrecentosessanta``).

The parser is bidirectional: ``parse(word)`` returns an ``int`` (or
``None`` if the word is not a recognised cardinal), and ``variants(n)``
returns the canonical written form. ``variants_for_unit(n, unit)``
emits every spelling variant the legal text might use for a quantity
of ``n`` together with the given temporal unit (``giorni`` / ``mesi``
/ ``anni`` / ...), including digit and word forms and singular /
plural permutations.
"""

from __future__ import annotations

import re
from typing import Iterable

_UNITS_BASE: dict[str, int] = {
    "zero": 0,
    "uno": 1,
    "un": 1,
    "una": 1,
    "due": 2,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "sei": 6,
    "sette": 7,
    "otto": 8,
    "nove": 9,
}

_TEENS: dict[str, int] = {
    "dieci": 10,
    "undici": 11,
    "dodici": 12,
    "tredici": 13,
    "quattordici": 14,
    "quindici": 15,
    "sedici": 16,
    "diciassette": 17,
    "diciotto": 18,
    "diciannove": 19,
}

_TENS_BASE: dict[str, int] = {
    "venti": 20,
    "trenta": 30,
    "quaranta": 40,
    "cinquanta": 50,
    "sessanta": 60,
    "settanta": 70,
    "ottanta": 80,
    "novanta": 90,
}

_HUNDREDS_BASE: dict[str, int] = {
    "cento": 100,
    "duecento": 200,
    "trecento": 300,
    "quattrocento": 400,
    "cinquecento": 500,
    "seicento": 600,
    "settecento": 700,
    "ottocento": 800,
    "novecento": 900,
}

_UNIT_WORDS = {
    1: "uno",
    2: "due",
    3: "tre",
    4: "quattro",
    5: "cinque",
    6: "sei",
    7: "sette",
    8: "otto",
    9: "nove",
}

_TENS_WORDS = {
    20: "venti",
    30: "trenta",
    40: "quaranta",
    50: "cinquanta",
    60: "sessanta",
    70: "settanta",
    80: "ottanta",
    90: "novanta",
}

_TEENS_WORDS = {
    10: "dieci",
    11: "undici",
    12: "dodici",
    13: "tredici",
    14: "quattordici",
    15: "quindici",
    16: "sedici",
    17: "diciassette",
    18: "diciotto",
    19: "diciannove",
}

_HUNDREDS_WORDS = {
    100: "cento",
    200: "duecento",
    300: "trecento",
    400: "quattrocento",
    500: "cinquecento",
    600: "seicento",
    700: "settecento",
    800: "ottocento",
    900: "novecento",
}


def _parse_under_100(word: str) -> int | None:
    if not word:
        return 0
    if word in _UNITS_BASE:
        return _UNITS_BASE[word]
    if word in _TEENS:
        return _TEENS[word]
    if word in _TENS_BASE:
        return _TENS_BASE[word]
    # tens with elided vowel before "uno" / "otto"
    # ventuno, ventotto, trentuno, trentotto, sessantuno, sessantotto, ...
    for tens_word, tens_val in _TENS_BASE.items():
        stem = tens_word[:-1]
        if word == stem + "uno":
            return tens_val + 1
        if word == stem + "otto":
            return tens_val + 8
        if word.startswith(tens_word):
            rest = word[len(tens_word):]
            unit = _UNITS_BASE.get(rest)
            if unit is not None and unit not in (1, 8):
                return tens_val + unit
    return None


def _parse_under_1000(word: str) -> int | None:
    if not word:
        return 0
    if word in _HUNDREDS_BASE:
        return _HUNDREDS_BASE[word]
    # cent[o]ottanta style: ``cento`` may elide its final ``o`` before vowels
    for hundreds_word, hundreds_val in _HUNDREDS_BASE.items():
        stem = hundreds_word[:-1]  # drop trailing 'o'
        if word == stem + "ottanta":
            return hundreds_val + 80
        if word == stem + "ottantuno":
            return hundreds_val + 81
        if word == stem + "ottantotto":
            return hundreds_val + 88
        if word.startswith(hundreds_word):
            rest = word[len(hundreds_word):]
            sub = _parse_under_100(rest)
            if sub is not None:
                return hundreds_val + sub
    return _parse_under_100(word)


def parse(word: str) -> int | None:
    """Parse a single Italian cardinal word (no spaces). Returns int or None."""

    if not word:
        return None
    w = word.lower().strip()
    if not w:
        return None
    if w.isdigit():
        try:
            return int(w)
        except ValueError:
            return None
    # mille / duemila / duemilatrecentosessanta etc.
    if w == "mille":
        return 1000
    if w.endswith("mila"):
        prefix = w[:-4]
        sub = _parse_under_1000(prefix)
        if sub is not None and sub > 0:
            return sub * 1000
    if "mila" in w and not w.startswith("mile"):
        idx = w.find("mila")
        head = w[:idx]
        tail = w[idx + 4 :]
        head_val = _parse_under_1000(head)
        if head_val is not None and head_val > 0:
            tail_val = _parse_under_1000(tail) if tail else 0
            if tail_val is not None:
                return head_val * 1000 + tail_val
    if w.startswith("mille"):
        rest = w[len("mille"):]
        sub = _parse_under_1000(rest)
        if sub is not None:
            return 1000 + sub
    return _parse_under_1000(w)


def _to_words_under_100(n: int) -> str:
    if n < 0 or n >= 100:
        raise ValueError(n)
    if n == 0:
        return ""
    if n < 10:
        return _UNIT_WORDS[n]
    if n < 20:
        return _TEENS_WORDS[n]
    tens = (n // 10) * 10
    unit = n % 10
    tens_word = _TENS_WORDS[tens]
    if unit == 0:
        return tens_word
    if unit in (1, 8):
        return tens_word[:-1] + _UNIT_WORDS[unit]
    return tens_word + _UNIT_WORDS[unit]


def _to_words_under_1000(n: int) -> str:
    if n < 0 or n >= 1000:
        raise ValueError(n)
    if n < 100:
        return _to_words_under_100(n)
    hundreds = (n // 100) * 100
    rest = n % 100
    hundreds_word = _HUNDREDS_WORDS[hundreds]
    if rest == 0:
        return hundreds_word
    rest_word = _to_words_under_100(rest)
    # elide trailing 'o' of cento/duecento/etc. before "ottanta" / "ottantuno" / "ottantotto"
    if rest_word.startswith("ottanta") or rest_word.startswith("ottant"):
        return hundreds_word[:-1] + rest_word
    return hundreds_word + rest_word


def to_words(n: int) -> str | None:
    """Return the canonical Italian written form for n in [0, 999_999]."""

    if not isinstance(n, int) or n < 0 or n > 999_999:
        return None
    if n == 0:
        return "zero"
    if n < 1000:
        return _to_words_under_1000(n)
    if n == 1000:
        return "mille"
    thousands = n // 1000
    rest = n % 1000
    if thousands == 1:
        head = "mille"
    else:
        head = _to_words_under_1000(thousands) + "mila"
    if rest == 0:
        return head
    return head + _to_words_under_1000(rest)


_UNIT_NORMALIZE: dict[str, str] = {
    "giorno": "giorni",
    "giorni": "giorni",
    "anno": "anni",
    "anni": "anni",
    "mese": "mesi",
    "mesi": "mesi",
    "settimana": "settimane",
    "settimane": "settimane",
    "ora": "ore",
    "ore": "ore",
}


def normalize_unit(unit: str) -> str:
    return _UNIT_NORMALIZE.get(unit.lower().strip(), unit.lower().strip())


_SINGULARS: dict[str, str] = {
    "giorni": "giorno",
    "anni": "anno",
    "mesi": "mese",
    "settimane": "settimana",
    "ore": "ora",
}


def variants_for_unit(value: int, unit: str) -> set[str]:
    """All lowercased "<n> <unit>" spellings of a numeric quantity.

    Useful when verifying a claim against raw source text: legal
    documents quote durations as digits and as words, in both singular
    and plural form. Returning the full superset lets the verifier do
    a single ``any(v in content for v in variants)`` check.
    """

    out: set[str] = set()
    plural = normalize_unit(unit)
    singular = _SINGULARS.get(plural, plural)
    units = {plural, singular}
    digit = str(value)
    word = to_words(value)
    for u in units:
        out.add(f"{digit} {u}")
        if word:
            out.add(f"{word} {u}")
    return out


_NUMBER_WORD_RE = re.compile(
    r"\b("
    r"[0-9]+|"
    r"mille|"
    r"[a-zà-ÿ]+mila[a-zà-ÿ]*|"
    r"mille[a-zà-ÿ]+|"
    r"(?:duecent|trecent|quattrocent|cinquecent|seicent|settecent|ottocent|novecent|cent)[oa]?[a-zà-ÿ]*|"
    r"(?:venti|trenta|quaranta|cinquanta|sessanta|settanta|ottanta|novanta)[a-zà-ÿ]*|"
    r"dici(?:assette|otto|annove)|"
    r"un[oa]?|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|"
    r"undici|dodici|tredici|quattordici|quindici|sedici"
    r")\b",
    flags=re.IGNORECASE,
)


def find_numbers_in_text(text: str) -> Iterable[tuple[int, str, str]]:
    """Yield (value, raw_word, raw_word_lower) for every parseable number."""

    for match in _NUMBER_WORD_RE.finditer(text):
        raw = match.group(1)
        value = parse(raw)
        if value is None:
            continue
        yield value, raw, raw.lower()
