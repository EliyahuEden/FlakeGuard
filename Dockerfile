FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY .streamlit ./.streamlit
COPY examples ./examples
COPY scripts ./scripts
COPY docs/evidence/commerceguard.json ./docs/evidence/commerceguard.json
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-deps . \
    && useradd --create-home flakeguard && mkdir -p /app/.runtime && chown -R flakeguard:flakeguard /app
USER flakeguard
EXPOSE 8000 8501
CMD ["uvicorn", "flakeguard.api:app", "--host", "0.0.0.0", "--port", "8000"]
