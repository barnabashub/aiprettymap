"""Turn the app state into a rendered prettymapp figure.

This is the bridge between our friendly parameter schema and prettymapp's own
API: it fetches the OpenStreetMap data, builds the draw settings (theme + the
user's color overrides) and produces a matplotlib figure.
"""

from __future__ import annotations

import colorsys
import copy
from functools import lru_cache
from typing import Any

from matplotlib.figure import Figure
from prettymapp.geo import get_aoi
from prettymapp.osm import get_osm_geometries
from prettymapp.plotting import Plot
from prettymapp.settings import STYLES

from .schema import normalize_hex

# Maps our canonical color-layer keys to the prettymapp draw-settings group and
# the specific key inside that group that holds the fill color.
_LAYER_TO_PRETTYMAPP = {
    "water": ("water", "fc"),
    "green": ("grassland", "fc"),
    "forest": ("woodland", "fc"),
    "street": ("streets", "fc"),
}


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in rgb))


def _building_cmap(hex_color: str) -> list[str]:
    """Build a 3-shade colormap (light → dark) from a single building color.

    prettymapp colors buildings from a gradient (``cmap``), which gives the map
    its lively look, so we synthesize shades instead of a single flat color.
    """
    r, g, b = _hex_to_rgb(hex_color)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    shades = []
    for factor in (1.25, 1.0, 0.7):  # lighter, base, darker
        nv = max(0.0, min(1.0, v * factor))
        shades.append(_rgb_to_hex(colorsys.hsv_to_rgb(h, s, nv)))
    return shades


def build_draw_settings(style_name: str, color_overrides: dict[str, str]) -> dict:
    """Return a prettymapp draw-settings dict: a chosen theme + color overrides."""
    draw = copy.deepcopy(STYLES.get(style_name, STYLES["Peach"]))

    for layer, hex_color in color_overrides.items():
        norm = normalize_hex(hex_color)
        if norm is None:
            continue
        if layer == "building":
            draw["urban"]["cmap"] = _building_cmap(norm)
        elif layer in _LAYER_TO_PRETTYMAPP:
            group, key = _LAYER_TO_PRETTYMAPP[layer]
            draw[group][key] = norm
        # "background" is handled separately (it is a Plot argument, not draw setting)
    return draw


@lru_cache(maxsize=16)
def _fetch_osm_cached(address: str, radius: int, rectangular: bool):
    """Fetch OSM geometries. Cached so repeated re-styling does not re-download."""
    aoi = get_aoi(address=address, radius=radius, rectangular=rectangular)
    df = get_osm_geometries(aoi=aoi)
    return df, tuple(aoi.bounds)


def make_figure(state: dict[str, Any]) -> Figure:
    """Render the map described by ``state`` and return a matplotlib Figure.

    Network / geocoding / "no data" errors are raised by prettymapp
    (``GeoCodingError``, ``OsmDataError``); the caller is expected to handle them.
    """
    rectangular = state["shape"] == "rectangle"
    df, bounds = _fetch_osm_cached(state["address"], int(state["radius"]), rectangular)

    draw = build_draw_settings(state["style"], state.get("colors", {}))

    caption = state.get("name") or state["address"]
    bg_color = state.get("colors", {}).get("background")

    plot = Plot(
        df=df,
        aoi_bounds=list(bounds),
        draw_settings=draw,
        shape=state["shape"],
        name_on=bool(state.get("name_on", True)),
        name=caption,
        bg_color=normalize_hex(bg_color) if bg_color else "#F2F4CB",
        # A lower dpi keeps memory/CPU light; still sharp enough for the web.
        dpi=150,
    )
    return plot.plot_all()
