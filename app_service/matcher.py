import json
from difflib import SequenceMatcher
from pathlib import Path

PHRASE_ERROR = "'phrase' must be a non-empty string."


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def load_phrases(path: str | Path) -> list[str]:
    phrases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(phrases, list) or not phrases:
        raise ValueError("Phrase file must be a non-empty JSON array.")
    if not all(isinstance(p, str) for p in phrases):
        raise ValueError("Every phrase must be a string.")
    return phrases


def find_closest(query: str, phrases: list[str]) -> tuple[str, float]:
    query_norm = normalize(query)
    best_phrase = phrases[0]
    best_score = -1.0
    for phrase in phrases:
        score = SequenceMatcher(None, query_norm, normalize(phrase)).ratio()
        if score > best_score:
            best_phrase, best_score = phrase, score
    return best_phrase, round(best_score, 2)


def extract_phrase(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError(PHRASE_ERROR)
    phrase = payload.get("phrase")
    if not isinstance(phrase, str) or not phrase.strip():
        raise ValueError(PHRASE_ERROR)
    return phrase.strip()
