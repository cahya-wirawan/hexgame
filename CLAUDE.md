# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hex board game implemented as a FastAPI WebSocket server with matchmaking, server-authoritative gameplay, best-of series, win detection, reconnect tokens, configurable first-player, and an optional Redis/PostgreSQL state backend. `PLAN.md` is the original design spec; Phases 1–8 are implemented. `README.md` is the user-facing docs.

Phase 8 adds a browser play page (`/play`) with live human vs human matchmaking, an in-browser DQN bot (greedy / minimax / MCTS modes, board sizes 5–13), and an in-browser AlphaZero bot (MCTS with configurable simulations, board sizes 5–11). Both bots run fully in the browser via ONNX Runtime Web; the server serves ONNX model files from `/models/`.

The repo is a **monorepo with two installable Python distributions**, each in its own subdirectory:

- `client/` → distribution **`hexgame`**, console command **`hexgame`** (subcommands: `random`, `play`, `gui`).
- `server/` → distribution **`hexgame-server`**, console command **`hexgame-server`** (uvicorn wrapper).

They share no runtime code and depend on each other only conceptually (via the WebSocket protocol). Each has its own `pyproject.toml`, `MANIFEST.in`, `README.md`, and `__version__` (in `client/src/hexgame/__init__.py` and `server/src/hexgame_server/__init__.py`).

## Commands

```bash
# Editable install of both distributions with all extras + test tools.
python -m pip install -r requirements.txt
# Equivalent: pip install -e "./client[gui,dev]" -e "./server[all,dev]"

# Or install only one side:
pip install -e "./client[gui,dev]"
pip install -e "./server[all,dev]"

# Run the server (thin wrapper around `uvicorn hexgame_server.main:app`)
hexgame-server --port 8000 [--reload] [--workers N] [--host 0.0.0.0]

# Clients
hexgame random --board-size 7 --server ws://localhost:8000
hexgame play   --model-name model_random --board-size 7
hexgame gui    --model-name human --board-size 7        # needs the [gui] extra

# Tests (root pyproject sets pythonpath=["client/src", "server/src"], so
# the in-memory tests need no install; redis/postgres tests need those extras.)
python -m pytest
python -m pytest tests/test_slots.py -v
python -m pytest tests/test_slots.py::test_slot_resets_after_disconnect -v

# Build each distribution (sdist + wheel)
python -m build --outdir dist client
python -m build --outdir dist server
```

## Packaging layout

`src/` layout for both subprojects. Each `pyproject.toml` declares dynamic version via `[tool.setuptools.dynamic]` `version = { attr = "<pkg>.__version__" }`.

- `client/src/hexgame/` — import `hexgame.<module>`. Entry point `hexgame` → `hexgame.__main__:main`, a subcommand dispatcher (`random` → `random_client`, `play` → `model_client`, `gui` → `gui_client`). The dispatcher prints a `hexgame <version> — <kind> client` banner before dispatching. `--model-name` resolution lives in `hexgame.model_client.load_model` and tries, in order: a filesystem path (`/` or `.py` in the name → `importlib.util.spec_from_file_location`, with the file's parent dir added to `sys.path` so sibling imports work), `hexgame.models.<NAME>`, `<NAME>` on `sys.path`, then `examples.<NAME>`. Transitive `ModuleNotFoundError`s from inside resolved modules are not swallowed. `hexgame play` and `hexgame gui` both accept `--slot-id` + `--reconnect-token` and route to `/ws/reconnect`; the token is printed to stdout on first `joined` and recorded in the replay log. `--username` defaults to `getpass.getuser()` (see `_default_username` in `model_client.py`).
- `server/src/hexgame_server/` — import `hexgame_server.<module>`. Entry point `hexgame-server` → `hexgame_server.__main__:main` (wraps uvicorn). The built Vite dashboard lives in `server/src/hexgame_server/static/overview/` and is shipped as package data; `frontend/vite.config.ts` builds into it. ONNX model files for the browser bots live in `server/src/hexgame_server/static/models/` (shipped as package data). `server/setup.py` is a setuptools `build_py` hook that runs `npm run build` before packaging unless `HEXGAME_SKIP_FRONTEND_BUILD=1` is set (used in the Dockerfile's runtime stage, which has no Node).
- Core deps: client → only `websockets`. Server → `fastapi`, `uvicorn[standard]`, `websockets`. Optional extras: client `[gui]` (pygame); server `[redis]` / `[postgres]` / `[all]`.
- `examples/` is **not** packaged — heavy/optional ML models (`model_alphazero`, `model_dqn*`), `.pt` weights, and the `hex_mcts` C++ extension live there for repo-checkout use only.

When moving/renaming server modules: internal imports are relative (`from .config import ...`); tests import absolute (`from hexgame_server.X import ...`).

## Server architecture

```
Client A <--WebSocket--> FastAPI Server <--WebSocket--> Client B
                              |
                         SlotManager (MAX_SLOTS slots, asyncio.Lock)
```

- `main.py` — routes, global `slot_manager`, static/landing/overview/statistics/play serving, `/health`, `/slots`, `/api/statistics`, `/play`, `/ws/join-slot`. Mounts `/models` as a static directory for ONNX files. Accepts optional `first_player` query param on `/ws/matchmake`.
- `config.py` — `MAX_SLOTS`, `ALLOWED_BOARD_SIZES = {7,9,11,13,19}`, allowed series lengths, `PROTOCOL_VERSION`, `PLAYER_1 = -1` / `PLAYER_2 = 1`, `PLAYER_COLORS`, `RECONNECT_TIMEOUT_SECONDS`, Redis/DB env config.
- `models.py` — `GameSlot`, `PlayerConnection`, `SlotAssignment`, `HexGameState`, `MatchSeriesState`. `MatchSeriesState` has an `initial_first_player` field (default `PLAYER_1`) that controls which player moves first in game 1; `first_turn()` alternates per game number. `GameSlot.snapshot()` is the canonical public view (used by `/slots` and the `reconnected.slot` payload). The lighter `websocket_manager._slot_labels_from_slot` walks `slot.player_{1,2}` directly to avoid building a full snapshot when only `player_models` / `player_usernames` are needed (e.g. inside `game_start`).
- `protocol.py` — message parsing + outgoing message factories.
- `slots.py` — `SlotManager`: matchmaking, locking, slot lifecycle, best-of series. `join_slot()` accepts a `first_player: int = PLAYER_1` parameter that is stored in `MatchSeriesState.initial_first_player`. `redis_slots.py` — `RedisSlotManager` subclass for shared state; also serialises/deserialises `initial_first_player`.
- `game.py` — move validation, win detection (BFS/DFS).
- `websocket_manager.py` — receive loop, message bridging, disconnect/reconnect handling. `_safe_send` and `_reset_after_reconnect_timeout` both catch `WebSocketDisconnect` in addition to `RuntimeError` so server-side navigation-away events do not produce tracebacks.
- `database.py` — SQLAlchemy ORM + completed-series repository (only active when `HEX_DATABASE_URL` is set).

### Key invariants

- **Player IDs are numeric**: `-1` (player_1, red, left↔right) and `1` (player_2, blue, top↔bottom). Board access is `board[r][q]`; neighbor offsets `[(+1,0),(-1,0),(0,+1),(0,-1),(+1,-1),(-1,+1)]`.
- **Server-authoritative identity**: clients never send `player` in `move`; the server adds it. Matchmaking + seat assignment happen atomically under `SlotManager`'s `asyncio.Lock` — do not `await websocket.send_json(...)` while holding that lock.
- **Messages**: `{"type": ..., "payload": {...}}`, `payload` always present. See `README.md` "WebSocket Protocol" for the full set (`joined`, `game_start`, `move`, `series_update`, `series_over`, `reconnected`, ...). `game_start` and the `reconnected.slot` snapshot carry `player_models` and `player_usernames` (keys are JSON-stringified player IDs: `"-1"` and `"1"`). The GUI uses these for the **Opponent** panel row — see `hexgame.gui_client.opponent_label_from`.
- **First player**: `MatchSeriesState.initial_first_player` (default `PLAYER_1`) determines who moves first in game 1. `first_turn()` returns `initial_first_player` for odd games and the opposite for even games. Set via the `first_player` query param on `/ws/matchmake`.
- **GUI niceties**: between games of a series the GUI holds the previous final board for `--match-delay` seconds (default 3.0, SPACE to skip) with the winner's path highlighted by **black hex fill** (`COLORS["winning_cell"]`, makes red/blue stones pop). `compute_winning_path` mirrors `hexgame_server.game.check_winner` but tracks BFS parents. Threaded through every `viewer.draw(...)` call via the `winning_path` / `opponent_label` kwargs.
- **State backend**: in-memory `memory` backend is single-process only; use `HEX_STATE_BACKEND=redis` before `hexgame-server --workers N`.
- **Reconnect**: on disconnect a seat is held for `RECONNECT_TIMEOUT_SECONDS`; the client returns via `/ws/reconnect?slot_id=...&token=...` with the token from its `joined` payload.
- **WebSocketDisconnect**: `_safe_send` and `_reset_after_reconnect_timeout` in `websocket_manager.py` catch both `RuntimeError` and `WebSocketDisconnect` so navigating away in the browser does not print tracebacks.

## Frontend

`frontend/` (Vite + React + TS + Tailwind). `npm run build` writes the production bundle into `server/src/hexgame_server/static/overview/`, which FastAPI serves at `/`, `/docs`, `/overview`, `/statistics`, and `/play`. `npm run dev` proxies `/slots`, `/api/statistics`, and `/models` to `http://127.0.0.1:8000`.

Key frontend files added in Phase 8:
- `frontend/src/pages/PlayPage.tsx` — browser play page: Lobby (mode selection, board size, series length, first-player picker) and GameBoard view. Shared `isBotGame` / `pendingBotJoin` ref pattern pairs the bot WebSocket with the human WebSocket via `/ws/join-slot`.
- `frontend/src/hooks/useDqnBot.ts` — DQN bot React hook. Exports `DqnBotPhase` and `BotMode = "dqn" | "minimax" | "mcts"`. Loads `dqn_{N}x{N}.onnx` via ONNX Runtime Web (wasm backend). Greedy: highest Q-value. Minimax: 2-ply negamax α-β (`MINIMAX_DEPTH=2`), Q-sorted move ordering, transposition cache. MCTS: 200 sims (`MCTS_N_SIMS=200`), PUCT (`MCTS_C_PUCT=1.5`), softmax Q-value prior (`MCTS_TEMP_PRIOR=1.0`).
- `frontend/src/hooks/useAlphaZeroBot.ts` — AlphaZero MCTS bot React hook. Exports `AZBotPhase`. Loads `alphazero_{N}x{N}.onnx` (ResNet, policy_logits + value outputs). PUCT MCTS (`AZ_C_PUCT=1.5`), configurable `nSims` (25/50/100/200/400, default 100). Perspective encoding identical to DQN: `perspIdx(r,q,player,n)`.
- `frontend/vite.config.ts` — `resolve.conditions: ["onnxruntime-web-use-extern-wasm"]` selects the extern-WASM build of ORT (WASM loaded from CDN, not bundled).

### Browser bot coordinate conventions

Both bot hooks use the same perspective encoding as the Python `model_alphazero.py`:
- Network input: `(1, 2, N, N)` float32 — channel 0 = my stones, channel 1 = opponent stones, always from current player's POV as red (left↔right).
- For `PLAYER_2` (blue), board is rotated: `perspBoard[pr][pc] = serverBoard[n-1-pc][n-1-pr]`.
- `perspIdx(r, q, player, n)`: `PLAYER_1` → `r*n+q`; `PLAYER_2` → `(n-1-q)*n + (n-1-r)`.

### ONNX model export

```bash
# DQN: input "board" (1,2,N,N) → output "q_values" (1,N²). Sizes 5,7,9,11,13,15.
python examples/export_dqn_onnx.py

# AlphaZero: input "board" (1,2,N,N) → outputs "policy_logits" (1,N²), "value" (1,). Sizes 5,7,9,11.
python examples/export_alphazero_onnx.py
```

Both scripts write to `server/src/hexgame_server/static/models/`. `export_alphazero_onnx.py` infers architecture from the checkpoint's `state_dict` (channels from `stem.0.weight.shape[0]`, blocks by counting `trunk.N.net.0.weight` keys) because the `.pt` files lack explicit metadata.

## Docker

`server/Dockerfile` is a multi-stage build: Node 20 for the frontend, then Python 3.12 for the server. `docker-compose.yml` lives at the repo root and references `context: .` + `dockerfile: server/Dockerfile`, so paths inside the Dockerfile are relative to the repo root (`frontend/...`, `server/...`).
