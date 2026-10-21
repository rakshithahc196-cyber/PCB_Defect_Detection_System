"""Locate a visible PCB with OpenRouter vision before defect inference."""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.8-flash"
KEY_FILE = Path(__file__).with_name(".env.local")


class BoardLocatorError(Exception):
    """The vision provider could not return a usable PCB region."""


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    if KEY_FILE.exists():
        for line in KEY_FILE.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "OPENROUTER_API_KEY":
                return value.strip().strip('"\'')
    return ""


def parse_region(content: str) -> dict | None:
    """Validate the model's 0–1000 image box and return normalized coordinates."""
    try:
        answer = json.loads(content)
        if type(answer["pcb_present"]) is not bool:
            raise ValueError("Invalid presence value")
        if not answer["pcb_present"]:
            return None
        x1, y1, x2, y2 = (answer[key] for key in ("x1", "y1", "x2", "y2"))
        if not all(type(value) is int for value in (x1, y1, x2, y2)):
            raise ValueError("Invalid box coordinates")
        if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000):
            raise ValueError("Box outside image")
        if x2 - x1 < 50 or y2 - y1 < 50:
            raise ValueError("PCB region too small")
    except (KeyError, TypeError, ValueError) as exc:
        raise BoardLocatorError("OpenRouter returned an invalid PCB region") from exc

    # A little context keeps edge defects inside the crop without admitting much background.
    pad_x = max(5, round((x2 - x1) * 0.03))
    pad_y = max(5, round((y2 - y1) * 0.03))
    left, top = max(0, x1 - pad_x), max(0, y1 - pad_y)
    right, bottom = min(1000, x2 + pad_x), min(1000, y2 + pad_y)
    return {"x": left / 1000, "y": top / 1000, "w": (right - left) / 1000, "h": (bottom - top) / 1000}


def locate_pcb(image: Image.Image, model: str | None = None) -> dict | None:
    key = api_key()
    if not key:
        raise BoardLocatorError("OpenRouter key is not configured")

    preview = image.copy()
    preview.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    encoded = io.BytesIO()
    preview.save(encoded, format="JPEG", quality=82)
    data_url = "data:image/jpeg;base64," + base64.b64encode(encoded.getvalue()).decode("ascii")
    fields = {
        "pcb_present": {"type": "boolean", "description": "True only when an electronic printed circuit board is clearly visible."},
        "x1": {"type": "integer", "description": "Left edge of the PCB, from 0 to 1000 across the image; use 0 if absent."},
        "y1": {"type": "integer", "description": "Top edge of the PCB, from 0 to 1000 down the image; use 0 if absent."},
        "x2": {"type": "integer", "description": "Right edge of the PCB, from 0 to 1000 across the image; use 0 if absent."},
        "y2": {"type": "integer", "description": "Bottom edge of the PCB, from 0 to 1000 down the image; use 0 if absent."},
    }
    selected_model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    free_model = selected_model.endswith(":free") or selected_model == "openrouter/free"
    payload = {
        "model": selected_model,
        "temperature": 0,
        "max_tokens": 700 if free_model else 400,
        "response_format": {"type": "json_object"} if free_model else {
            "type": "json_schema",
            "json_schema": {
                "name": "pcb_region", "strict": True,
                "schema": {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False},
            },
        },
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    "Find the visible electronic printed circuit board (PCB) in this image. "
                    "Reply as one JSON object with exactly pcb_present (boolean) and x1, y1, x2, y2 (integers). "
                    "Return its tight bounding rectangle in image coordinates scaled from 0 to 1000. "
                    "If a PCB is displayed on a monitor or phone, bound only the PCB content, not the screen, bezel, desk, or dark surroundings. "
                    "If multiple PCBs are visible, choose the largest clear board. "
                    "Set pcb_present to false and all coordinates to zero unless traces or electronic components make a PCB clearly identifiable."
                )},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
    }
    if not free_model:
        payload["provider"] = {"require_parameters": True}
    request = Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            result = json.load(response)
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Unexpected response content")
        return parse_region(content)
    except HTTPError as exc:
        raise BoardLocatorError(f"OpenRouter returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise BoardLocatorError("OpenRouter is temporarily unreachable") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise BoardLocatorError("OpenRouter returned an unreadable response") from exc
