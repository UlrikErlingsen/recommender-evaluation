FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ARROW_DEFAULT_MEMORY_POOL=system

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY app.py ./
COPY assets ./assets
COPY examples ./examples
COPY docs ./docs
RUN useradd --create-home --uid 10001 recommendsignal && chown -R recommendsignal:recommendsignal /app
USER recommendsignal

EXPOSE 8587
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8587/_stcore/health')"
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.headless=true", "--server.address=0.0.0.0", "--server.port=8587"]
