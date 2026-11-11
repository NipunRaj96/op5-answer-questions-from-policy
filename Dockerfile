# Build needs network (PyPI). Running needs only the model gateway.
#   docker build -t policy-book .
#   docker run -p 8000:8000 -v /path/to/corpus:/corpus:ro -e CORPUS_DIR=/corpus \
#     -e LLM_BASE_URL=https://api.groq.com/openai/v1 -e LLM_API_KEY=... policy-book
# Default model: qwen/qwen3.8-27b (the only one tested). Override with GEN_MODEL / GEN_EXTRA.
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY scripts/reproduce.sh scripts/
USER nobody
ENV PORT=8000
CMD ["scripts/reproduce.sh", "serve"]
