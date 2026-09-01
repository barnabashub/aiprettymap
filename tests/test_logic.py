"""Lightweight tests for the pure logic (no network / no AI calls).

Run with:  pytest -q
"""

from PIL import Image

from aiprettymap import colors, schema
from aiprettymap.nlp import _extract_json


# --------------------------- schema.apply_changes --------------------------- #
def test_apply_valid_changes():
    state = schema.default_state()
    new_state, applied, rejected = schema.apply_changes(
        state,
        {
            "address": "Budapest",
            "radius": 1500,
            "shape": "rectangle",
            "style": "Auburn",
            "colors": {"water": "#123456"},
        },
    )
    assert new_state["address"] == "Budapest"
    assert new_state["radius"] == 1500
    assert new_state["shape"] == "rectangle"
    assert new_state["style"] == "Auburn"
    assert new_state["colors"]["water"] == "#123456"
    assert applied and not rejected


def test_radius_is_clamped():
    state = schema.default_state()
    new_state, _, _ = schema.apply_changes(state, {"radius": 999999})
    assert new_state["radius"] == schema.RADIUS_MAX


def test_invalid_values_rejected_not_crashing():
    state = schema.default_state()
    _, applied, rejected = schema.apply_changes(
        state,
        {"shape": "triangle", "style": "Nope", "colors": {"water": "banana"}},
    )
    assert not applied
    assert len(rejected) == 3


def test_case_insensitive_matching():
    state = schema.default_state()
    new_state, applied, _ = schema.apply_changes(
        state, {"shape": "CIRCLE", "style": "peach"}
    )
    assert new_state["shape"] == "circle"
    assert new_state["style"] == "Peach"
    assert applied


def test_reset_colors():
    state = schema.default_state()
    state["colors"] = {"water": "#000000"}
    new_state, applied, _ = schema.apply_changes(state, {"reset_colors": True})
    assert new_state["colors"] == {}
    assert applied


# ------------------------------- color tools -------------------------------- #
def test_normalize_hex():
    assert schema.normalize_hex("#abc") == "#aabbcc"
    assert schema.normalize_hex("112233") == "#112233"
    assert schema.normalize_hex("not-a-color") is None


def test_palette_extraction_and_mapping():
    # A synthetic image with clear blue, green and dark regions.
    img = Image.new("RGB", (90, 30))
    for x in range(90):
        for y in range(30):
            if x < 30:
                img.putpixel((x, y), (30, 80, 220))    # blue
            elif x < 60:
                img.putpixel((x, y), (40, 160, 60))     # green
            else:
                img.putpixel((x, y), (20, 20, 20))      # near-black
    palette = colors.extract_palette(img, n_colors=4)
    assert palette
    layers = colors.palette_to_layers(palette)
    # Water should be the bluest, street the darkest.
    assert "water" in layers
    assert "street" in layers


# ------------------------------- nlp helpers -------------------------------- #
def test_extract_json_plain():
    assert _extract_json('{"changes": {"radius": 500}, "unsupported": []}') == {
        "changes": {"radius": 500},
        "unsupported": [],
    }


def test_extract_json_with_code_fence():
    text = '```json\n{"changes": {}, "unsupported": ["x"]}\n```'
    assert _extract_json(text) == {"changes": {}, "unsupported": ["x"]}


def test_extract_json_embedded_in_prose():
    text = 'Sure! Here you go: {"changes": {"shape": "circle"}} thanks'
    assert _extract_json(text) == {"changes": {"shape": "circle"}}
