# Runs the whole pipeline (load, dbt build and tests, dbt docs) in a fixed environment:
# the exact base image below (Debian Linux, Python 3.12.10) and the pinned packages in
# requirements.txt.
# Build:  docker build -t gss-pipeline .
# Run:    docker run --rm -v "<repo>/output:/app/output" gss-pipeline
# Everything a run produces is written to /app/output, so mount a folder there to keep it.

# The digest fixes the image itself: a tag can be republished with different contents.
FROM python:3.12.10-slim@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db

WORKDIR /app

# Install packages first so this layer is reused when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The database, pipeline log, dbt logs and dbt output (docs, run_results.json) all outlive
# the container, so a run can be inspected, and a failure explained, after it exits.
ENV GSS_DB_PATH=/app/output/gss.duckdb \
    GSS_LOG_DIR=/app/output/logs \
    DBT_LOG_PATH=/app/output/dbt_logs \
    DBT_TARGET_PATH=/app/output/dbt_target

CMD ["python", "source/pipeline/run_pipeline.py"]
