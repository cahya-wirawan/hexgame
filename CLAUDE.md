# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI-based WebSocket server for the Hex board game. Manages fixed game slots and bridges real-time communication between two players. See `PLAN.md` for the full implementation specification.

## Commands

Once `requirements.txt` and `app/` are created:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (single process only — do not use multiple workers with in-memory state)
uvicorn app.main:app --reload

# Run all tests
pytest

# Run a single test file
pytest tests/test_slots.py -v

# Run a single test
pytest tests/test_slots.py::test_slot_resets_after_disconnect -v
```

Testing WebSocket endpoints requires `pytest-asyncio` and FastAPI's `TestClient`/`AsyncClient`.

## Architecture

```
Client A <--WebSocket--> FastAPI Server <--WebSocket--> Client B
                              |
                         SlotManager (5 slots)
```

**Module layout** (`app/`):
- `main.py` — FastAPI app, route registration, global `SlotManager` singleton
- `config.py` — `MAX_SLOTS = 5`, `ALLOWED_BOARD_SIZES = {7, 9, 11, 13, 19}`, `PROTOCOL_VERSION = 1`
- `models.py` — `GameSlot`, `PlayerConnection`, `HexGameState` dataclasses
- `protocol.py` — JSON message parsing and outgoing message factories
- `slots.py` — `SlotManager`: matchmaking, locking, slot lifecycle
- `game.py` — move validation, turn tracking, BFS/DFS win detection
- `websocket_manager.py` — receive loop, message forwarding, disconnect handling

**Examples** (`examples/`):
- `random_client.py` — reference client that connects to `/ws/matchmake` and plays uniformly random legal moves. Used as smoke test, stress test, and protocol reference. Run two instances with the same `--board-size` to exercise a full game end-to-end. See `PLAN.md` §28.

### Key Design Decisions

**Matchmaking endpoint**: `/ws/matchmake?board_size=11` — matchmaking and join happen atomically in the WebSocket handshake (not via a prior HTTP reservation).

**Slot states**: `empty → waiting → full`. A slot resets fully to `empty` on any disconnect.

**Concurrency**: All slot mutations go through `asyncio.Lock` inside `SlotManager.join_slot()` to prevent two clients from claiming the same player seat.

**Player identity**: Server-authoritative. The server assigns `player_1`/`player_2` based on join order. Clients must not send a `player` field in move messages — the server adds it from the WebSocket context.

**Message protocol**: All messages are `{"type": "...", "payload": {...}}`. Server→client types: `joined`, `waiting_for_opponent`, `game_start`, `move`, `move_rejected`, `opponent_disconnected`, `game_over`, `error`. Client→server types: `hello`, `move` (only `{q, r}`), `chat`, `resign`, `ping`.

**Win detection**: BFS/DFS on a hex grid. `player_1` wins by connecting top edge to bottom edge; `player_2` wins left edge to right edge. Neighbors use offsets `[(+1,0),(-1,0),(0,+1),(0,-1),(+1,-1),(-1,+1)]`. Board coordinates: `board[r][q]`, `0 <= q,r < board_size`.

**Single-process constraint**: `SlotManager` is in-memory. Never run multiple Uvicorn workers until Phase 7 (Redis) is implemented.

### Development Phases

Implement in this order (see `PLAN.md` §25–27 for details):
1. Slot model + `SlotManager` + HTTP endpoints (`/health`, `/slots`)
2. WebSocket matchmaking + `joined`/`waiting_for_opponent`/`game_start` messages
3. Message bridge (forward client messages to opponent with trusted metadata)
4. Authoritative `HexGameState` + move validation + turn tracking
5. Win detection (`game_over` broadcast)
6. Reconnect support (`reconnect_token`, `/ws/reconnect`)
7. Redis + database for distributed deployment

**First milestone**: Two clients with the same `board_size` pair into a slot and can exchange JSON messages in real time (Phases 1–3).
