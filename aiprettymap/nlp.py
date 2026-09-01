"""Natural-language instruction parsing via a Hugging Face model.

The user types a free-text instruction (e.g. "show me Budapest with blue water and
a rectangular shape"). We send that instruction — together with the current map
state — to a hosted Hugging Face chat model and ask it to return a small JSON
"patch" describing which parameters to change. The app then validates and applies
that patch (see ``schema.apply_changes``).

Using a *hosted* model (Hugging Face Inference Providers) means no model runs on
the local machine, so this works on a small free-tier server with only an API
token.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from huggingface_hub import InferenceClient

from .schema import COLOR_LAYERS, RADIUS_MAX, RADIUS_MIN, SHAPES, STYLE_PRESETS

# A capable, freely hosted instruction model that is good at emitting JSON.
# Override with the HF_MODEL environment variable if you prefer another one.
DEFAULT_MODEL = os.environ.get("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")

# Which Hugging Face Inference Provider to route through. "auto" lets HF pick any
# available provider for the model; set HF_PROVIDER to pin a specific one
# (e.g. "hf-inference", "together", "nebius").
PROVIDER = os.environ.get("HF_PROVIDER", "auto")

_SYSTEM_PROMPT = f"""You translate a user's free-text request into a JSON patch that \
changes a stylized map. You NEVER answer in prose — you only output JSON.

The map has these adjustable settings:
- "address": string, any place/address to center the map on.
- "radius": integer meters, from {RADIUS_MIN} to {RADIUS_MAX}.
- "shape": one of {SHAPES}.
- "style": one of {STYLE_PRESETS} (built-in color themes).
- "name_on": boolean, whether to print a title on the image.
- "name": string, the title text (empty string means "use the address").
- "colors": an object mapping any of these layers {COLOR_LAYERS} to a hex color \
like "#3388ff". "green" = grass/parks, "forest" = woods, "street" = roads, \
"building" = houses, "background" = the paper/base color.
- "reset_colors": boolean true to clear custom colors and go back to the theme.

Rules:
1. Output ONLY a single JSON object, no markdown, no explanation.
2. The object has two keys: "changes" (an object with only the settings the user \
wants changed) and "unsupported" (a list of strings describing any part of the \
request you cannot map to the settings above).
3. Only include settings in "changes" that the user actually asked to change.
4. Interpret relative requests using the CURRENT STATE (e.g. "make it bigger" \
increases radius, "zoom out" increases radius, "no title" sets name_on=false).
5. Convert color names to hex (e.g. "blue"->"#3388ff", "dark green"->"#1b5e20").
6. If nothing in the request maps to a setting, return {{"changes": {{}}, \
"unsupported": ["...why..."]}}.
"""


@dataclass
class ParseResult:
    """Outcome of parsing one instruction."""

    changes: dict[str, Any]
    unsupported: list[str]
    error: str | None = None  # set when the AI call itself failed

    @property
    def ok(self) -> bool:
        return self.error is None


def _extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort: pull the first JSON object out of the model's reply."""
    # Strip common markdown code fences.
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: grab the outermost {...} block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _friendly_error(exc: Exception) -> str:
    """Turn a raw Inference exception into an actionable message for the user."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc)

    if status == 403 or "sufficient permissions" in text or "Forbidden" in text:
        return (
            "Your Hugging Face token can't call Inference Providers (403). "
            "Create a fine-grained token at huggingface.co/settings/tokens and "
            "enable the 'Make calls to Inference Providers' permission (Inference "
            "section), then use that token. If it persists, check your free "
            "inference credits at huggingface.co/settings/billing."
        )
    if status == 401 or "invalid" in text.lower() and "token" in text.lower():
        return "Hugging Face token looks invalid (401). Double-check you pasted it correctly."
    if status == 404 or "not found" in text.lower():
        return (
            f"The model '{DEFAULT_MODEL}' isn't available via the selected provider "
            "(404). Try another model in the sidebar, e.g. "
            "'meta-llama/Llama-3.1-8B-Instruct' or 'mistralai/Mistral-7B-Instruct-v0.3'."
        )
    if status in (429, 503) or "rate" in text.lower() or "loading" in text.lower():
        return "The model is busy or rate-limited right now. Wait a moment and try again."
    return f"Could not reach the AI model ({type(exc).__name__}): {exc}"


def parse_instruction(
    instruction: str,
    current_state: dict[str, Any],
    token: str | None = None,
    model: str | None = None,
) -> ParseResult:
    """Send one instruction to the model and return a validated ParseResult."""
    token = token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    if not token:
        return ParseResult(
            changes={},
            unsupported=[],
            error="No Hugging Face token configured. Add HF_TOKEN to use the AI.",
        )

    model = model or DEFAULT_MODEL

    # Only send the parts of the state the model needs to resolve relative requests.
    state_summary = {
        "address": current_state.get("address"),
        "radius": current_state.get("radius"),
        "shape": current_state.get("shape"),
        "style": current_state.get("style"),
        "name_on": current_state.get("name_on"),
        "name": current_state.get("name"),
        "colors": current_state.get("colors", {}),
    }

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"CURRENT STATE:\n{json.dumps(state_summary)}\n\n"
                f"USER REQUEST:\n{instruction}"
            ),
        },
    ]

    try:
        client = InferenceClient(api_key=token, provider=PROVIDER)
        completion = client.chat_completion(
            messages=messages,
            model=model,
            max_tokens=400,
            temperature=0.1,
        )
        reply = completion.choices[0].message.content or ""
    except Exception as exc:  # network / auth / provider errors
        return ParseResult(changes={}, unsupported=[], error=_friendly_error(exc))

    data = _extract_json(reply)
    if data is None:
        return ParseResult(
            changes={},
            unsupported=[],
            error="The AI returned a response I couldn't understand. Try rephrasing.",
        )

    changes = data.get("changes") or {}
    unsupported = data.get("unsupported") or []
    if not isinstance(changes, dict):
        changes = {}
    if not isinstance(unsupported, list):
        unsupported = [str(unsupported)]

    return ParseResult(changes=changes, unsupported=[str(u) for u in unsupported])
