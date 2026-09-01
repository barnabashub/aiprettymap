"""State schema, defaults and validation for the map parameters.

This module is the single source of truth for *what* can be controlled on the
map. Both the AI instruction parser (`nlp.py`) and the UI (`app.py`) rely on the
constants and helpers defined here, so the AI can never set a value that the map
renderer cannot handle.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from prettymapp.settings import STYLES

# Built-in color themes shipped with prettymapp (Peach, Auburn, Citrus, Flannel).
STYLE_PRESETS: list[str] = list(STYLES.keys())

# User-facing map shapes -> value expected by prettymapp's Plot.shape.
SHAPES: list[str] = ["circle", "rectangle"]

# Canonical color layer keys the user (and the AI) can recolor. These are our own
# friendly names; `mapmaker.py` translates them to prettymapp's draw settings.
COLOR_LAYERS: list[str] = [
    "building",   # houses / built-up areas   -> prettymapp "urban"
    "water",      # rivers, lakes, sea        -> prettymapp "water"
    "green",      # grass, parks, fields      -> prettymapp "grassland"
    "forest",     # woods                     -> prettymapp "woodland"
    "street",     # roads, railways           -> prettymapp "streets"
    "background",  # paper / base color        -> Plot.bg_color
]

# Bounds for the map radius in meters. Kept modest so a single map stays fast to
# fetch and light on memory (this is meant to run on a small free-tier machine).
RADIUS_MIN = 200
RADIUS_MAX = 3000

# The default map shown on first load.
DEFAULT_STATE: dict[str, Any] = {
    "address": "Praça do Comércio, Lisbon",
    "radius": 1100,
    "shape": "circle",
    "style": "Peach",
    "name_on": True,
    "name": "",                 # empty -> the address is used as the caption
    "colors": {},               # canonical layer key -> "#RRGGBB"
}

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def default_state() -> dict[str, Any]:
    """Return a fresh deep copy of the default state."""
    return copy.deepcopy(DEFAULT_STATE)


def normalize_hex(value: str) -> str | None:
    """Return a normalized ``#RRGGBB`` string, or ``None`` if not a valid color."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v.startswith("#"):
        v = "#" + v
    if not _HEX_RE.match(v):
        return None
    # Expand shorthand (#abc -> #aabbcc) so downstream code only sees 6 digits.
    if len(v) == 4:
        v = "#" + "".join(ch * 2 for ch in v[1:])
    return v.lower()


def _match_choice(value: str, choices: list[str]) -> str | None:
    """Case-insensitive membership check returning the canonical spelling."""
    if not isinstance(value, str):
        return None
    for c in choices:
        if value.strip().lower() == c.lower():
            return c
    return None


def apply_changes(
    state: dict[str, Any], changes: dict[str, Any]
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Validate ``changes`` and merge the accepted ones into a copy of ``state``.

    Returns ``(new_state, applied, rejected)`` where ``applied`` and ``rejected``
    are human-readable strings describing what happened. Invalid values are simply
    skipped (and reported), never crash the app.
    """
    new_state = copy.deepcopy(state)
    applied: list[str] = []
    rejected: list[str] = []

    if not isinstance(changes, dict):
        return new_state, applied, ["Invalid change payload."]

    for key, value in changes.items():
        if value is None:
            continue

        if key == "address":
            if isinstance(value, str) and value.strip():
                new_state["address"] = value.strip()
                applied.append(f"location → {value.strip()}")
            else:
                rejected.append("empty location")

        elif key == "radius":
            try:
                r = int(round(float(value)))
            except (TypeError, ValueError):
                rejected.append(f"radius '{value}' is not a number")
                continue
            r = max(RADIUS_MIN, min(RADIUS_MAX, r))
            new_state["radius"] = r
            applied.append(f"radius → {r} m")

        elif key == "shape":
            m = _match_choice(value, SHAPES)
            if m:
                new_state["shape"] = m
                applied.append(f"shape → {m}")
            else:
                rejected.append(f"unknown shape '{value}'")

        elif key == "style":
            m = _match_choice(value, STYLE_PRESETS)
            if m:
                new_state["style"] = m
                applied.append(f"theme → {m}")
            else:
                rejected.append(f"unknown theme '{value}'")

        elif key == "name_on":
            new_state["name_on"] = bool(value)
            applied.append(f"title {'on' if value else 'off'}")

        elif key == "name":
            if isinstance(value, str):
                new_state["name"] = value.strip()
                applied.append("title text updated")

        elif key == "colors":
            if not isinstance(value, dict):
                rejected.append("colors must be a mapping")
                continue
            for layer, hex_value in value.items():
                layer_key = _match_choice(layer, COLOR_LAYERS)
                if layer_key is None:
                    rejected.append(f"unknown color layer '{layer}'")
                    continue
                norm = normalize_hex(hex_value)
                if norm is None:
                    rejected.append(f"invalid color '{hex_value}' for {layer}")
                    continue
                new_state["colors"][layer_key] = norm
                applied.append(f"{layer_key} color → {norm}")

        elif key == "reset_colors":
            if value:
                new_state["colors"] = {}
                applied.append("colors reset to theme defaults")

        else:
            rejected.append(f"unsupported setting '{key}'")

    return new_state, applied, rejected
