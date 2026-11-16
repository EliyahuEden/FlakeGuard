# Stage 1: build the React workspace into src/flakeguard/web.
FROM node:22-slim AS web
WORKDIR /build
COPY web/package.json web/package-lock.json ./web/
RUN cd web && npm ci --no-audit --no-fund
COPY web ./web
RUN mkdir -p src/flakeguard && cd web && npm run build

# Stage 2: API and bundled workspace on one origin.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
COPY --from=web /build/src/flakeguard/web ./src/flakeguard/web
COPY migrations ./migrations
COPY alembic.ini ./
COPY examples ./examples
COPY scripts ./scripts
COPY docs/evidence/commerceguard.json ./docs/evidence/commerceguard.json
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-deps . \
    && useradd --create-home flakeguard && mkdir -p /app/.runtime && chown -R flakeguard:flakeguard /app
USER flakeguard
EXPOSE 8000
CMD ["uvicorn", "flakeguard.api:app", "--host", "0.0.0.0", "--port", "8000"]
