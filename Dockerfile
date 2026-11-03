# Runs the whole pipeline (load, dbt build and tests, dbt docs) in a fixed environment:
# the exact Python version below, the pinned packages in requirements.txt, and Debian Linux.
# Build:  docker build -t gss-pipeline .
# Run:    docker run --rm -v "<repo>/output:/app/output" gss-pipeline
# The database and logs are written to /app/output, so mount a folder there to keep them.

FROM python:3.12.10-slim

WORKDIR /app

# Install packages first so this layer is reused when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV GSS_DB_PATH=/app/output/gss.duckdb \
    GSS_LOG_DIR=/app/output/logs

CMD ["python", "source/pipeline/run_pipeline.py"]
