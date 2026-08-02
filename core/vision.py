import json
import re

from PIL import Image

from . import transport


def _prompt():
    return (
        "Analyze this 2D architectural floor plan image. "
        "Extract the overall plan dimensions (width x depth) and, for every room, "
        "its name and its printed dimensions. Return ONLY a compact JSON object "
        "with keys 'overall' and 'rooms' (rooms is an array of {name, dims}). "
        "No markdown, no commentary."
    )


def _clean(text):
    if not text:
        return None
    candidates = [text]
    for m in re.finditer(r"\{.*\}", text, re.S):
        candidates.append(m.group(0))
    for cand in candidates:
        for _ in range(3):
            if not cand:
                break
            try:
                return json.loads(cand, strict=False)
            except Exception:
                match = re.search(r"\{.*\}", cand, re.S)
                if not match or match.group(0) == cand:
                    break
                cand = match.group(0)
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


def extract(values, image_bytes):
    model = transport.model(values, "K3", 1400)
    image = Image.open(image_bytes)
    image.load()
    content = None
    last = None
    for attempt in range(3):
        try:
            response = model([{
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt()},
                    {"type": "image", "image": image},
                ],
            }])
            content = response.content
        except Exception as e:
            last = e
            continue
        if content:
            parsed = _unwrap(str(content))
            if parsed:
                return parsed
    raise RuntimeError(f"Could not read the uploaded floor plan image. {last or ''}")
