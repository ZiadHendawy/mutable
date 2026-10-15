FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Download the embedding model once, here, so no request or test run has to. It goes
# outside /app because docker compose mounts the repo over /app, which would hide it.
# fastembed reads FASTEMBED_CACHE_PATH, so the running app finds the model here too.
# The model name must match MODEL_NAME in app/embeddings.py.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
