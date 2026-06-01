import json
from pathlib import Path

TRANSLATIONS_DIR = Path(__file__).parent / "translations"
SUPPORTED_LANGUAGES = ["en", "de"]
DEFAULT_LANGUAGE = "en"

_translations: dict[str, dict[str, str]] = {}


def load_translations() -> None:
    """Load all translation files from the translations directory."""
    for lang in SUPPORTED_LANGUAGES:
        filepath = TRANSLATIONS_DIR / f"{lang}.json"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                _translations[lang] = json.load(f)


def get_translations(lang: str) -> dict[str, str]:
    """Get translations for a given language, falling back to default."""
    if not _translations:
        load_translations()
    if lang in _translations:
        return _translations[lang]
    return _translations.get(DEFAULT_LANGUAGE, {})


def detect_language(accept_language: str | None, cookie_lang: str | None) -> str:
    """Detect language from cookie override or Accept-Language header."""
    # Cookie/manual selection takes priority
    if cookie_lang and cookie_lang in SUPPORTED_LANGUAGES:
        return cookie_lang

    # Parse Accept-Language header
    if accept_language:
        for part in accept_language.split(","):
            lang_tag = part.split(";")[0].strip().lower()
            # Check exact match
            if lang_tag in SUPPORTED_LANGUAGES:
                return lang_tag
            # Check prefix (e.g. "de-DE" -> "de")
            prefix = lang_tag.split("-")[0]
            if prefix in SUPPORTED_LANGUAGES:
                return prefix

    return DEFAULT_LANGUAGE


# Load on import
load_translations()
