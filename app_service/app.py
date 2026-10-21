import logging
from pathlib import Path

from flask import Flask, jsonify, request

from matcher import extract_phrase, find_closest, load_phrases

app = Flask(__name__)

PHRASES = load_phrases(Path(__file__).parent / "phrases.json")


def error_response(message: str, status_code: int):
    return jsonify({"error": message}), status_code


@app.post("/match")
def match():
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response("Request body must be valid JSON.", 400)

    try:
        phrase = extract_phrase(payload)
    except ValueError as err:
        return error_response(str(err), 400)

    try:
        best, score = find_closest(phrase, PHRASES)
    except Exception:
        logging.exception("Matching failed")
        return error_response("Internal server error.", 500)

    return jsonify({"match": best, "score": score})
