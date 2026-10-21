import json
import logging
from pathlib import Path

import azure.functions as func

from matcher import extract_phrase, find_closest, load_phrases

app = func.FunctionApp()

PHRASES = load_phrases(Path(__file__).parent / "phrases.json")


def error_response(message: str, status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": message}),
        status_code=status_code,
        mimetype="application/json",
    )


@app.route(route="match", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def match(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
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

    return func.HttpResponse(
        json.dumps({"match": best, "score": score}),
        mimetype="application/json",
    )
