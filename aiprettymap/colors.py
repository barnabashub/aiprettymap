"""Extract a characteristic color palette from an uploaded image and map those
colors onto the map's layers.

No heavy dependencies (no scikit-learn): we use Pillow's median-cut quantization
to find the dominant colors, then a small set of heuristics to decide which color
best fits each map layer (water = the bluest color, forest = a dark green, etc.).
"""

from __future__ import annotations

import colorsys
from typing import Iterable

from PIL import Image

RGB = tuple[int, int, int]


def _rgb_to_hex(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def extract_palette(image: Image.Image, n_colors: int = 6) -> list[RGB]:
    """Return up to ``n_colors`` dominant RGB colors, most frequent first."""
    img = image.convert("RGB")
    # Downscale first: we only need dominant colors, and this keeps it fast/light.
    img.thumbnail((200, 200))
    quantized = img.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    # getcolors returns (count, palette_index) pairs.
    counts = quantized.getcolors() or []
    counts.sort(reverse=True)  # most frequent first

    colors: list[RGB] = []
    for _count, idx in counts:
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        colors.append((r, g, b))
    return colors


def _hsv(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (c / 255.0 for c in rgb)
    return colorsys.rgb_to_hsv(r, g, b)


def _blue_score(rgb: RGB) -> float:
    h, s, v = _hsv(rgb)
    # Hue near ~0.55 (cyan/blue). Reward saturation, penalize distance from blue.
    dist = min(abs(h - 0.58), 1 - abs(h - 0.58))
    return (1 - dist * 2) * (0.3 + s)


def _green_score(rgb: RGB) -> float:
    h, s, v = _hsv(rgb)
    dist = min(abs(h - 0.33), 1 - abs(h - 0.33))
    return (1 - dist * 2) * (0.3 + s)


def _brightness(rgb: RGB) -> float:
    r, g, b = rgb
    # Perceived luminance.
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _shift_lightness(rgb: RGB, factor: float) -> RGB:
    """Return a lighter (factor>1) or darker (factor<1) variant of a color."""
    h, s, v = _hsv(rgb)
    v = max(0.0, min(1.0, v * factor))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (round(r * 255), round(g * 255), round(b * 255))


def palette_to_layers(palette: list[RGB]) -> dict[str, str]:
    """Map a dominant-color palette onto the canonical map color layers.

    Heuristics (each color can be reused if the palette is small):
      * background -> the most dominant, fairly light color
      * water      -> the bluest color
      * forest     -> the greenest / a dark green
      * green      -> a lighter green (or a lightened forest color)
      * street     -> the darkest color
      * building   -> a saturated mid-tone that is not already water/green
    """
    if not palette:
        return {}

    layers: dict[str, str] = {}

    # background: prefer a light, dominant color.
    bg = max(palette[:3], key=_brightness)
    layers["background"] = _rgb_to_hex(bg)

    # water: bluest color in the palette.
    water = max(palette, key=_blue_score)
    if _blue_score(water) > 0.15:
        layers["water"] = _rgb_to_hex(water)

    # forest / green: greenest color, plus a lighter variant for grassland.
    greenest = max(palette, key=_green_score)
    if _green_score(greenest) > 0.1:
        layers["forest"] = _rgb_to_hex(greenest)
        layers["green"] = _rgb_to_hex(_shift_lightness(greenest, 1.25))

    # street: darkest color (roads read best as the darkest ink on the map).
    street = min(palette, key=_brightness)
    layers["street"] = _rgb_to_hex(street)

    # building: a saturated mid-tone that is not the water or main green color.
    used = {layers.get("water"), layers.get("forest"), layers.get("green")}
    candidates = [c for c in palette if _rgb_to_hex(c) not in used]
    if candidates:
        building = max(candidates, key=lambda c: _hsv(c)[1])  # most saturated
        layers["building"] = _rgb_to_hex(building)

    return layers


def hexes(palette: list[RGB]) -> list[str]:
    """Convenience: palette as a list of hex strings (for showing swatches)."""
    return [_rgb_to_hex(c) for c in palette]
