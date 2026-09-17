FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY scripts ./scripts
COPY neo4j/import ./neo4j/import

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000"]
