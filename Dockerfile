FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libreoffice-writer \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-chi-sim \
    tesseract-ocr-hin \
    tesseract-ocr-tam \
    tesseract-ocr-mal \
    tesseract-ocr-kan \
    tesseract-ocr-tel \
    fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser app/ app/
COPY --chown=appuser:appuser skills/ skills/
COPY --chown=appuser:appuser mcp_servers/ mcp_servers/

USER appuser

ENV PORT=8000
EXPOSE 8000

# Fargate/ECS may inject PORT; default remains 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
