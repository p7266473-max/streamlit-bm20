import json
import re

from . import transport


def _clean(text):
    if not text:
        return None
    candidates = [text]
    for m in re.finditer(r"\{.*\}", text, re.S):
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            return json.loads(cand, strict=False)
        except Exception:
            continue
    return None


def _unwrap(text):
    parsed = _clean(text)
    if parsed is None:
        return None
    while isinstance(parsed, dict) and "answer" in parsed:
        inner = parsed["answer"]
        if isinstance(inner, str):
            parsed = _clean(inner)
        else:
            parsed = inner
    return parsed


def _prompt(spec_text):
    return (
        "Convert the following building specification text into a clean, structured "
        "JSON object for a structural backend. Return ONLY JSON with keys 'overall' "
        "(string: overall plan size) and 'rooms' (array of {\"name\": string, "
        "\"dims\": string}). Preserve the dimensions exactly as written, in their "
        "original units. Do not invent rooms that are not listed. No markdown, "
        "no commentary.\n\n"
        f"BUILDING SPECIFICATION:\n{spec_text}"
    )


def parse(values, spec_text):
    model = transport.model(values, "K3", 1400)
    last = None
    for attempt in range(3):
        try:
            response = model([{"role": "user", "content": _prompt(spec_text)}])
            content = response.content
        except Exception as e:
            last = e
            continue
        if content:
            parsed = _unwrap(str(content))
            if parsed and isinstance(parsed, dict) and parsed.get("rooms"):
                return parsed
    raise RuntimeError(f"Could not parse the specification text into a room layout. {last or ''}")
