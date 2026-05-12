FROM node:20-slim AS overview-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

COPY frontend ./frontend
RUN mkdir -p /build/src/hexgame/server/static && cd frontend && npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEX_STATE_BACKEND=memory

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin hexgame

# Install the package (with redis + postgres extras) from source.
# The frontend bundle is built in the node stage and copied in, so the
# setup.py build hook must not try to run npm here (no Node in this stage).
COPY pyproject.toml setup.py README.md PLAN.md ./
COPY src ./src
COPY --from=overview-build /build/src/hexgame/server/static/overview ./src/hexgame/server/static/overview
RUN python -m pip install --no-cache-dir --upgrade pip \
    && HEXGAME_SKIP_FRONTEND_BUILD=1 python -m pip install --no-cache-dir ".[redis,postgres]"

USER hexgame

EXPOSE 8000

CMD ["hexgame-server", "--host", "0.0.0.0", "--port", "8000"]
