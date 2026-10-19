FROM node:22-alpine AS frontend
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.18
COPY . .
RUN uv sync --frozen --no-dev
COPY --from=frontend /web/dist ./web/dist
EXPOSE 8001
CMD ["uv", "run", "--no-sync", "uvicorn", "forge.api:app", "--host", "0.0.0.0", "--port", "8001"]
