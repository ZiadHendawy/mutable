FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Download the embedding model once, here, so no request or test run has to. Only the
# embeddings module is copied in first, so editing other code doesn't download it again.
# The model goes outside /app because docker compose mounts the repo over /app, which
# would hide it. fastembed reads FASTEMBED_CACHE_PATH, so the running app finds it too.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
COPY app/__init__.py app/embeddings.py app/
RUN python -c "from app.embeddings import LocalEmbedder; LocalEmbedder()"
# From here on, never download: if the model is missing, loading it fails loudly.
ENV HF_HUB_OFFLINE=1

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
