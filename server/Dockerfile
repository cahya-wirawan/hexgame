# Build the overview frontend, then install the hexgame-server package.
# Build context is the repo root (see docker-compose.yml), so paths below
# are relative to the repository, not to server/.

FROM node:20-slim AS overview-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

COPY frontend ./frontend
# vite outputs to ../server/src/hexgame_server/static/overview/, so the dir
# must exist before the build runs.
RUN mkdir -p /build/server/src/hexgame_server/static \
    && cd frontend && npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEX_STATE_BACKEND=memory

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin hexgame

# Copy only what the server distribution needs.
COPY server/pyproject.toml server/setup.py ./server/
COPY README.md PLAN.md ./
COPY server/src ./server/src
COPY --from=overview-build \
     /build/server/src/hexgame_server/static/overview \
     ./server/src/hexgame_server/static/overview

# Frontend bundle is already copied in; skip the build hook (no Node here).
RUN python -m pip install --no-cache-dir --upgrade pip \
    && HEXGAME_SKIP_FRONTEND_BUILD=1 \
       python -m pip install --no-cache-dir "./server[redis,postgres]"

USER hexgame

EXPOSE 8000

CMD ["hexgame-server", "--host", "0.0.0.0", "--port", "8000"]
