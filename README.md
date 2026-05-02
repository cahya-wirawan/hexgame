# Hex Game Server

FastAPI-based Hex game server with WebSocket matchmaking, authoritative game
state, win detection, a random-move test client, and a Vite/Tailwind/shadcn-ui
overview dashboard.

The current implementation covers Phases 1-5 from `PLAN.md`:

- Fixed in-memory game slots.
- Board-size-aware matchmaking.
- Best-of match series with configurable odd series lengths.
- WebSocket real-time gameplay.
- Server-authoritative move validation and turn tracking.
- Hex win detection.
- `/overview` monitoring page.

Reconnect support, Redis, database persistence, user accounts, ratings, and
multi-worker deployment are intentionally not implemented yet.

## Requirements

- Python 3.10+ recommended.
- Node.js 20+ recommended for the overview frontend.
- Single Uvicorn worker only. Slot and game state are stored in process memory.

Install backend dependencies:

```bash
python -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

## Running The Server

From the repository root:

```bash
python -m uvicorn app.main:app --port 8000
```

Then open:

- Health: `http://127.0.0.1:8000/health`
- Slot state JSON: `http://127.0.0.1:8000/slots`
- Overview dashboard: `http://127.0.0.1:8000/overview`

If WebSocket clients receive HTTP 404 on `/ws/matchmake`, restart Uvicorn after
installing `requirements.txt`. Uvicorn must start with WebSocket support
available.

## Frontend Overview

The dashboard lives in `frontend/` and is built with:

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui-style local components

During frontend development:

```bash
cd frontend
npm run dev
```

The Vite dev server proxies `/slots` to `http://127.0.0.1:8000`.

Build the production dashboard:

```bash
cd frontend
npm run build
```

The production build writes to `app/static/overview/`. FastAPI serves that
build at `/overview` and serves assets from `/overview/assets/...`.

## API

### HTTP

`GET /health`

Returns:

```json
{"status": "ok"}
```

`GET /slots`

Returns the current state of all slots. It is safe for clients and dashboards:
it does not include raw WebSocket objects or secrets.

Example:

```json
[
  {
    "slot_id": 1,
    "state": "full",
    "board_size": 11,
    "player_count": 2,
    "players": ["player_1", "player_2"],
    "current_turn": "player_1",
    "winner": null,
    "move_count": 8,
    "board": [[null, "player_1"]]
  }
]
```

`GET /overview`

Serves the built dashboard.

### WebSocket

`/ws/matchmake?board_size=11&series_length=3`

Allowed board sizes:

```text
7, 9, 11, 13, 19
```

Allowed series lengths:

```text
1, 3, 5, 7
```

`series_length` defaults to `1`. The server only matches players who request
the same board size and the same series length.

## WebSocket Protocol

Every message uses this shape:

```json
{
  "type": "message_type",
  "payload": {}
}
```

### Client To Server

`hello`

```json
{
  "type": "hello",
  "payload": {
    "protocol_version": 1,
    "client_name": "hex-client"
  }
}
```

`move`

Clients send only coordinates. The server assigns the player identity from the
WebSocket connection.

```json
{
  "type": "move",
  "payload": {
    "q": 3,
    "r": 5
  }
}
```

`chat`

```json
{
  "type": "chat",
  "payload": {
    "message": "Good luck!"
  }
}
```

`resign`

```json
{
  "type": "resign",
  "payload": {}
}
```

`ping`

```json
{
  "type": "ping",
  "payload": {}
}
```

### Server To Client

`joined`

```json
{
  "type": "joined",
  "payload": {
    "slot_id": 1,
    "player": "player_1",
    "color": "blue",
    "board_size": 11,
    "protocol_version": 1
  }
}
```

`waiting_for_opponent`

```json
{
  "type": "waiting_for_opponent",
  "payload": {
    "slot_id": 1,
    "board_size": 11
  }
}
```

`game_start`

```json
{
  "type": "game_start",
  "payload": {
    "slot_id": 1,
    "board_size": 11,
    "series_length": 3,
    "players": ["player_1", "player_2"],
    "first_turn": "player_1",
    "current_game_number": 1,
    "player_1_wins": 0,
    "player_2_wins": 0,
    "wins_required": 2
  }
}
```

`move`

```json
{
  "type": "move",
  "payload": {
    "player": "player_1",
    "q": 3,
    "r": 5,
    "next_turn": "player_2"
  }
}
```

`move_rejected`

```json
{
  "type": "move_rejected",
  "payload": {
    "reason": "Not your turn"
  }
}
```

`game_over`

```json
{
  "type": "game_over",
  "payload": {
    "winner": "player_1",
    "reason": "connected_sides"
  }
}
```

`series_update`

Sent after each completed game in a series.

```json
{
  "type": "series_update",
  "payload": {
    "player_1_wins": 1,
    "player_2_wins": 0,
    "current_game_number": 2,
    "wins_required": 2,
    "series_length": 3
  }
}
```

`series_over`

Sent when a player reaches the required number of wins.

```json
{
  "type": "series_over",
  "payload": {
    "winner": "player_1",
    "player_1_wins": 2,
    "player_2_wins": 0,
    "wins_required": 2,
    "series_length": 3
  }
}
```

Other server messages:

- `pong`
- `chat`
- `error`
- `opponent_disconnected`

## Gameplay Rules

- `player_1` is blue and moves first.
- `player_2` is red.
- A game is one Hex board.
- A series is best-of `1`, `3`, `5`, or `7` games between the same players.
- The series ends as soon as a player reaches `ceil(series_length / 2)` wins.
- First turn alternates by game number: odd games start with `player_1`, even
  games start with `player_2`.
- Coordinates are `(q, r)`.
- Board access is `board[r][q]`.
- `player_1` wins by connecting top to bottom.
- `player_2` wins by connecting left to right.
- Neighbors use the axial-like offsets:

```python
(+1, 0), (-1, 0), (0, +1), (0, -1), (+1, -1), (-1, +1)
```

The server rejects moves when:

- The game has not started.
- The game is already finished.
- It is not the sender's turn.
- Coordinates are outside the board.
- The target cell is occupied.
- The payload is malformed.

## Random Client

The reference client plays uniformly random legal moves. It is useful for
smoke testing matchmaking, gameplay, and win detection.

Start the server first:

```bash
python -m uvicorn app.main:app --port 8000
```

Run two clients in separate terminals:

```bash
python -m examples.random_client --board-size 11 --seed 1
python -m examples.random_client --board-size 11 --seed 2
```

Useful options:

```bash
python -m examples.random_client \
  --server ws://127.0.0.1:8000 \
  --board-size 11 \
  --series-length 3 \
  --seed 42 \
  --move-delay 0.1
```

There is also a helper script:

```bash
bash examples/run_pair.sh
```

## Tests

Run all backend tests:

```bash
python -m pytest
```

Run frontend build verification:

```bash
cd frontend
npm run build
```

The current test suite covers:

- Slot assignment and reset behavior.
- Board-size-aware matchmaking.
- Series-length-aware matchmaking and best-of scoring.
- Protocol validation.
- Move validation and turn order.
- Hex win detection.
- WebSocket matchmaking and gameplay.
- Overview endpoint serving.

## Project Layout

```text
app/
  main.py                FastAPI routes and global SlotManager
  config.py              Slot, board-size, protocol, and player constants
  models.py              GameSlot, PlayerConnection, SlotAssignment, HexGameState
  protocol.py            Message parsing and message factories
  slots.py               SlotManager and slot lifecycle
  game.py                Move validation and win detection
  websocket_manager.py   WebSocket receive loop and gameplay handling
  static/overview/       Built Vite dashboard

frontend/
  src/                   Vite React overview source
  package.json           Frontend scripts and dependencies

examples/
  random_client.py       Random-move WebSocket client
  run_pair.sh            Launches two random clients

tests/
  test_*.py              Unit and integration tests
```

## Operational Notes

- Run with one Uvicorn worker only. Multiple workers each get separate memory,
  so matchmaking and game state will split incorrectly.
- `/overview` is an operational/debug dashboard. Protect or disable it before
  exposing this service beyond a trusted local network.
- On any player disconnect, the current implementation notifies the opponent,
  closes the opponent connection, and resets the slot.
- Reconnect support is not implemented yet.

## Troubleshooting

### `/overview` is blank

Rebuild the frontend:

```bash
cd frontend
npm run build
```

The built `index.html` must reference assets under `/overview/assets/...`.

### Random client gets HTTP 404

Install backend requirements and restart Uvicorn:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

This usually means the server was started before WebSocket support was
available, or another app is listening on port 8000.

### Slot state looks stale

Restart the server. State is in-memory and intentionally resets on process
restart.
