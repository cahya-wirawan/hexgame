# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`hexgame` — a FastAPI WebSocket server for the Hex board game (fixed game slots, board-size + series-length matchmaking, server-authoritative moves, win detection, reconnect, optional Redis/PostgreSQL), packaged with two console commands plus reference clients. `PLAN.md` is the original design spec; Phases 1–7 are implemented. `README.md` is the user-facing docs.

## Commands

```bash
# Editable install with all optional backends + test tools
python -m pip install -e ".[dev,all]"      # or: pip install -r requirements.txt

# Run the server (thin wrapper around `uvicorn hexgame.server.main:app`)
hexgame-server --port 8000 [--reload] [--workers N] [--host 0.0.0.0]

# Clients
hexgame random --board-size 7 --server ws://localhost:8000
hexgame play   --model-name model_random --board-size 7
hexgame gui    --model-name human --board-size 7        # needs the [gui] extra

# Tests (pyproject sets pythonpath=src, so no install needed for the in-memory tests;
# the redis/postgres tests need those extras installed)
python -m pytest
python -m pytest tests/test_slots.py -v
python -m pytest tests/test_slots.py::test_slot_resets_after_disconnect -v

# Build distributions
python -m build            # -> dist/hexgame-*.tar.gz, dist/hexgame-*.whl
```

## Packaging layout

`src/` layout, distribution name `hexgame`, configured in `pyproject.toml` (setuptools, dynamic version from `hexgame.__version__`).

- `src/hexgame/server/` — the FastAPI app. Entry point `hexgame-server` → `hexgame.server.__main__:main` (wraps uvicorn). The built Vite dashboard lives in `src/hexgame/server/static/overview/` and is shipped as package data (`frontend/vite.config.ts` builds into it).
- `src/hexgame/client/` — reference clients. Entry point `hexgame` → `hexgame.client.__main__:main`, a subcommand dispatcher (`random` → `random_client`, `play` → `model_client`, `gui` → `gui_client`). `--model-name NAME` resolves via `hexgame.client.models.NAME` then a top-level `NAME` on `sys.path` (`hexgame.client.model_client.load_model`).
- Console entry points are in `[project.scripts]`; optional deps in `[project.optional-dependencies]` (`redis`, `postgres`, `gui`, `dev`, `all`). Core install pulls only `fastapi`, `uvicorn[standard]`, `websockets`.
- `examples/` is **not** packaged — heavy/optional ML models (`model_alphazero`, `model_dqn*`), `.pt` weights, and the `hex_mcts` C++ extension live there for repo-checkout use only.
- `MANIFEST.in` controls sdist contents; `requirements.txt` is just `-e .[all,dev]`.

When moving/renaming server modules, remember internal imports are relative (`from .config import ...`); tests import absolute (`from hexgame.server.X import ...`).

## Server architecture

```
Client A <--WebSocket--> FastAPI Server <--WebSocket--> Client B
                              |
                         SlotManager (MAX_SLOTS slots, asyncio.Lock)
```

- `main.py` — routes, global `slot_manager`, static/landing/overview/statistics serving, `/health`, `/slots`, `/api/statistics`.
- `config.py` — `MAX_SLOTS`, `ALLOWED_BOARD_SIZES = {7,9,11,13,19}`, allowed series lengths, `PROTOCOL_VERSION`, `PLAYER_1 = -1` / `PLAYER_2 = 1`, `PLAYER_COLORS`, `RECONNECT_TIMEOUT_SECONDS`, Redis/DB env config.
- `models.py` — `GameSlot`, `PlayerConnection`, `SlotAssignment`, `HexGameState`, `MatchSeriesState`.
- `protocol.py` — message parsing + outgoing message factories.
- `slots.py` — `SlotManager`: matchmaking, locking, slot lifecycle, best-of series. `redis_slots.py` — `RedisSlotManager` subclass for shared state.
- `game.py` — move validation, win detection (BFS/DFS).
- `websocket_manager.py` — receive loop, message bridging, disconnect/reconnect handling.
- `database.py` — SQLAlchemy ORM + completed-series repository (only active when `HEX_DATABASE_URL` is set).

### Key invariants

- **Player IDs are numeric**: `-1` (player_1, red, left↔right) and `1` (player_2, blue, top↔bottom). Board access is `board[r][q]`; neighbor offsets `[(+1,0),(-1,0),(0,+1),(0,-1),(+1,-1),(-1,+1)]`.
- **Server-authoritative identity**: clients never send `player` in `move`; the server adds it. Matchmaking + seat assignment happen atomically under `SlotManager`'s `asyncio.Lock` — do not `await websocket.send_json(...)` while holding that lock.
- **Messages**: `{"type": ..., "payload": {...}}`, `payload` always present. See `README.md` "WebSocket Protocol" for the full set (`joined`, `game_start`, `move`, `series_update`, `series_over`, `reconnected`, ...).
- **State backend**: in-memory `memory` backend is single-process only; use `HEX_STATE_BACKEND=redis` before `hexgame-server --workers N`.
- **Reconnect**: on disconnect a seat is held for `RECONNECT_TIMEOUT_SECONDS`; the client returns via `/ws/reconnect?slot_id=...&token=...` with the token from its `joined` payload.

## Frontend

`frontend/` (Vite + React + TS + Tailwind). `npm run build` writes the production bundle into `src/hexgame/server/static/overview/`, which FastAPI serves at `/`, `/docs`, `/overview`, `/statistics`. `npm run dev` proxies `/slots` and `/api/statistics` to `http://127.0.0.1:8000`.
