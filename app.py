"""AI PrettyMap — a Streamlit chat app that builds stylized maps from free text.

Type an instruction ("show me Budapest with blue water, rectangular shape"), and
a Hugging Face model turns it into map settings that prettymapp renders. Upload an
image and the app pulls its colors onto the map.
"""

from __future__ import annotations

import os
from io import BytesIO

import matplotlib

matplotlib.use("Agg")  # headless backend, no display needed on a server
import matplotlib.pyplot as plt
import streamlit as st
from PIL import Image

from aiprettymap import colors as color_tools
from aiprettymap import schema
from aiprettymap.mapmaker import make_figure
from aiprettymap.nlp import DEFAULT_MODEL, parse_instruction

# prettymapp raises these on bad locations / empty areas.
from prettymapp.geo import GeoCodingError
from prettymapp.osm import OsmDataError

st.set_page_config(page_title="AI PrettyMap", page_icon="🗺️", layout="wide")

EXAMPLE_PROMPTS = [
    "Show me Budapest, Hungary",
    "Zoom out a bit and use the Auburn theme",
    "Make the water dark blue and the streets black",
    "Rectangular shape, no title",
    "Reset the colors to the theme",
]


# --------------------------------------------------------------------------- #
# Session state helpers
# --------------------------------------------------------------------------- #
def init_session() -> None:
    if "state" not in st.session_state:
        st.session_state.state = schema.default_state()
    if "messages" not in st.session_state:
        st.session_state.messages = []  # list of {"role", "content"}
    if "png" not in st.session_state:
        st.session_state.png = None
    if "palette" not in st.session_state:
        st.session_state.palette = []
    if "last_upload_key" not in st.session_state:
        st.session_state.last_upload_key = None
    if "needs_render" not in st.session_state:
        st.session_state.needs_render = True  # render the default map on first load


def add_message(role: str, content: str) -> None:
    st.session_state.messages.append({"role": role, "content": content})


def render_png(state: dict) -> bytes:
    """Render the current state to PNG bytes (and free the matplotlib figure)."""
    fig = make_figure(state)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return buf.getvalue()


def regenerate() -> None:
    """Re-render the map for the current state, reporting errors to the chat."""
    try:
        with st.spinner("Building the map…"):
            st.session_state.png = render_png(st.session_state.state)
    except GeoCodingError as exc:
        add_message("assistant", f"⚠️ I couldn't find that location: {exc}")
    except OsmDataError as exc:
        add_message(
            "assistant",
            f"⚠️ There's no map data for that area (try a bigger radius): {exc}",
        )
    except Exception as exc:  # keep the app alive on any unexpected error
        add_message("assistant", f"⚠️ Something went wrong while drawing: {exc}")


# --------------------------------------------------------------------------- #
# Token resolution (secrets -> env -> sidebar input)
# --------------------------------------------------------------------------- #
def resolve_token() -> str | None:
    try:
        if "HF_TOKEN" in st.secrets:
            return st.secrets["HF_TOKEN"]
    except Exception:
        pass
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def render_sidebar() -> tuple[str | None, str]:
    with st.sidebar:
        st.header("⚙️ Settings")

        token = resolve_token()
        if not token:
            token = st.text_input(
                "Hugging Face token",
                type="password",
                help="Create a free token at huggingface.co/settings/tokens. "
                "You can also set it as the HF_TOKEN secret/env var.",
            ) or None
        else:
            st.success("Hugging Face token loaded ✓")

        model = st.text_input("Model", value=DEFAULT_MODEL)

        st.divider()
        st.subheader("🎨 Colors from an image")
        st.caption("Upload a picture and the map adopts its dominant colors.")
        upload = st.file_uploader(
            "Image", type=["png", "jpg", "jpeg"], label_visibility="collapsed"
        )
        handle_image_upload(upload)

        if st.session_state.palette:
            st.write("Extracted palette:")
            st.markdown(_swatches_html(st.session_state.palette), unsafe_allow_html=True)

        st.divider()
        st.subheader("Current map")
        s = st.session_state.state
        st.write(
            f"**Location:** {s['address']}  \n"
            f"**Radius:** {s['radius']} m  \n"
            f"**Shape:** {s['shape']}  \n"
            f"**Theme:** {s['style']}"
        )
        if s["colors"]:
            st.write("**Custom colors:** " + ", ".join(f"{k}" for k in s["colors"]))

        if st.button("↺ Reset everything"):
            st.session_state.state = schema.default_state()
            st.session_state.palette = []
            st.session_state.last_upload_key = None
            st.session_state.needs_render = True
            add_message("assistant", "Reset to defaults.")
            st.rerun()

    return token, model


def _swatches_html(hex_list: list[str]) -> str:
    boxes = "".join(
        f'<span style="display:inline-block;width:26px;height:26px;'
        f'background:{h};border:1px solid #999;border-radius:4px;margin:2px;"></span>'
        for h in hex_list
    )
    return f"<div>{boxes}</div>"


def handle_image_upload(upload) -> None:
    if upload is None:
        return
    key = f"{upload.name}:{upload.size}"
    if key == st.session_state.last_upload_key:
        return  # already processed this exact file
    st.session_state.last_upload_key = key
    try:
        image = Image.open(upload)
        palette = color_tools.extract_palette(image, n_colors=6)
        layer_colors = color_tools.palette_to_layers(palette)
        st.session_state.palette = color_tools.hexes(palette)
        st.session_state.state["colors"].update(layer_colors)
        st.session_state.needs_render = True
        add_message(
            "assistant",
            "🎨 Applied colors from your image: "
            + ", ".join(f"{k} = {v}" for k, v in layer_colors.items()),
        )
    except Exception as exc:
        add_message("assistant", f"⚠️ Couldn't read that image: {exc}")


# --------------------------------------------------------------------------- #
# Instruction handling
# --------------------------------------------------------------------------- #
def handle_instruction(prompt: str, token: str | None, model: str) -> None:
    add_message("user", prompt)

    result = parse_instruction(
        prompt, st.session_state.state, token=token, model=model
    )

    if not result.ok:
        add_message("assistant", f"⚠️ {result.error}")
        return

    new_state, applied, rejected = schema.apply_changes(
        st.session_state.state, result.changes
    )

    notes: list[str] = []
    if applied:
        st.session_state.state = new_state
        st.session_state.needs_render = True
        notes.append("✅ " + "; ".join(applied))
    # Things the AI itself flagged as impossible, plus values we rejected.
    problems = list(result.unsupported) + rejected
    if problems:
        notes.append("🤔 I couldn't do: " + "; ".join(problems))
    if not applied and not problems:
        notes.append(
            "I couldn't turn that into a map change. Try naming a place, a color, "
            "a shape (circle/rectangle) or a theme."
        )

    add_message("assistant", "  \n".join(notes))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    init_session()
    token, model = render_sidebar()

    st.title("🗺️ AI PrettyMap")
    st.caption(
        "Describe the map you want in plain language — the AI adjusts the settings "
        "and prettymapp draws it. No reply, it just reshapes the picture."
    )

    prompt = st.chat_input("e.g. 'Show me Budapest with blue water, rectangular'")
    if prompt:
        handle_instruction(prompt, token, model)

    # Render (or re-render) the map if something changed.
    if st.session_state.needs_render:
        st.session_state.needs_render = False
        regenerate()

    col_map, col_chat = st.columns([3, 2], gap="large")

    with col_map:
        if st.session_state.png:
            st.image(st.session_state.png, use_container_width=True)
            st.download_button(
                "⬇️ Download PNG",
                data=st.session_state.png,
                file_name="prettymap.png",
                mime="image/png",
            )
        else:
            st.info("No map yet. Type an instruction below to create one.")

    with col_chat:
        st.subheader("Conversation")
        if not st.session_state.messages:
            st.caption("Try one of these:")
            for ex in EXAMPLE_PROMPTS:
                st.markdown(f"- *{ex}*")
        for msg in st.session_state.messages[-12:]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])


if __name__ == "__main__":
    main()
