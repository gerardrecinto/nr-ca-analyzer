FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml .
COPY MANIFEST.in .
COPY ca_analyzer/ ./ca_analyzer/

RUN pip install --no-cache-dir .

ENTRYPOINT ["nr-ca-analyzer"]
