# Minimal image to run the AI PrettyMap Streamlit app.
# The Python geo/plotting stack (osmnx, geopandas, shapely, matplotlib) ships
# manylinux wheels, so no extra system libraries are required.
FROM python:3.11-slim

# Streamlit + Python runtime niceties.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application code.
COPY . .

EXPOSE 8501

# HF_TOKEN is provided at runtime, e.g.:
#   docker run -p 8501:8501 -e HF_TOKEN=hf_xxx aiprettymap
HEALTHCHECK CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8501/_stcore/health'); " || exit 1

CMD ["streamlit", "run", "app.py"]
