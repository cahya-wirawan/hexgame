# Hex Game Server

FastAPI-based Hex game server with WebSocket matchmaking, authoritative game
state, win detection, a random-move test client, and a Vite/Tailwind/shadcn-ui
frontend with a landing page plus an operational overview dashboard.

The current implementation covers Phases 1-7 from `PLAN.md`:

- Fixed in-memory game slots.
- Board-size-aware matchmaking.
- Best-of match series with configurable odd series lengths.
- WebSocket real-time gameplay.
- Server-authoritative move validation and turn tracking.
- Hex win detection.
- `/` project landing page, `/docs` usage guide, and `/overview` monitoring page.
- Model-driven clients, including a pygame GUI client for visual board output.
- Reconnect tokens and `/ws/reconnect` support for temporary network drops.
- Optional Redis-backed slot, game, session, and reconnect-token state.
- Optional PostgreSQL/SQLAlchemy completed-series history.

User accounts and ratings are intentionally not implemented yet.

## Requirements

- Python 3.10+ recommended.
- Node.js 20+ recommended for the overview frontend.
- `pygame` is required for `examples/hex_client_gui.py`.
- Redis is optional. The default backend is still in-process memory for local
  development.
- PostgreSQL is optional. Completed-series history is disabled unless
  `HEX_DATABASE_URL` is set.

Install backend dependencies:

```bash
python -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

## Using The Hosted Server

The model clients default to the hosted arena:

```text
wss://hexgame.codingdojo.ai
```

That means users can install the client dependencies, add or choose a model,
and connect directly without running their own FastAPI server:

```bash
python -m pip install -r requirements.txt
python -m examples.hex_client --model-name model_random --board-size 7
python -m examples.hex_client_gui --model-name human --board-size 7
```

Open:

- Landing page: `https://hexgame.codingdojo.ai/`
- Documentation: `https://hexgame.codingdojo.ai/docs`
- Overview dashboard: `https://hexgame.codingdojo.ai/overview`

## Running A Local Server

From the repository root:

```bash
python -m uvicorn app.main:app --port 8000
```

Then open:

- Health: `http://127.0.0.1:8000/health`
- Slot state JSON: `http://127.0.0.1:8000/slots`
- Landing page: `http://127.0.0.1:8000/`
- Documentation: `http://127.0.0.1:8000/docs`
- Overview dashboard: `http://127.0.0.1:8000/overview`
- OpenAPI/Swagger UI: `http://127.0.0.1:8000/api/docs`

Point clients at the local server with `--server`:

```bash
python -m examples.hex_client --model-name model_random --board-size 7 --server ws://localhost:8000
python -m examples.hex_client_gui --model-name human --board-size 7 --server ws://localhost:8000
```

If WebSocket clients receive HTTP 404 on `/ws/matchmake`, restart Uvicorn after
installing `requirements.txt`. Uvicorn must start with WebSocket support
available.

## Docker Compose

Build and run the server with Redis and PostgreSQL:

```bash
docker compose up --build
```

Compose starts:

- `app`: FastAPI server on `http://127.0.0.1:8000`
- `redis`: active slot/game/session/reconnect-token state
- `postgres`: completed-series history through SQLAlchemy ORM

Stop the stack:

```bash
docker compose down
```

Remove persisted Redis/PostgreSQL data:

```bash
docker compose down -v
```

## Redis State Backend

By default, state is stored in memory:

```bash
python -m uvicorn app.main:app --port 8000
```

To persist active slot state in Redis and share slot/game/session/reconnect
state between server processes, start Redis and run:

```bash
HEX_STATE_BACKEND=redis \
HEX_REDIS_URL=redis://127.0.0.1:6379/0 \
python -m uvicorn app.main:app --port 8000
```

Redis stores active slots, board state, series score, public model names,
connection status, and reconnect tokens. Raw WebSocket objects are never stored
in Redis; after a server restart, persisted players are marked disconnected and
can return through `/ws/reconnect` using their reconnect token.

Use `HEX_REDIS_KEY_PREFIX` to isolate environments that share the same Redis
database.

## Database History

Completed series can be written through SQLAlchemy ORM to PostgreSQL. Set
`HEX_DATABASE_URL` before starting the server:

```bash
HEX_DATABASE_URL=postgresql+psycopg://hex:hex@127.0.0.1:5432/hexgame \
python -m uvicorn app.main:app --port 8000
```

By default, `HEX_DATABASE_AUTO_CREATE=1` creates the `completed_series` table on
startup. Set `HEX_DATABASE_AUTO_CREATE=0` if migrations or external schema
management should own table creation.

The completed-series record stores slot id, board size, series length, winner,
score, public model names, final board, and the final public slot snapshot. It
does not store reconnect tokens or WebSocket objects.

## Frontend

The landing page and overview dashboard live in `frontend/` and are built with:

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

The production build writes to `app/static/overview/`. FastAPI serves the
landing page at `/`, the documentation page at `/docs`, the dashboard at `/overview`, and assets from
`/overview/assets/...`.

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
    "series_length": 3,
    "player_count": 2,
    "connected_player_count": 2,
    "players": [-1, 1],
    "player_models": {"-1": "model_alphazero", "1": "human"},
    "connected_players": [-1, 1],
    "disconnected_players": [],
    "current_turn": -1,
    "winner": null,
    "move_count": 8,
    "board": [[null, -1]],
    "wins_required": 2,
    "current_game_number": 1,
    "player_1_wins": 0,
    "player_2_wins": 0,
    "series_winner": null
  }
]
```

`GET /`

Serves the built landing page.

`GET /docs`

Serves the built project documentation page.

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
1, 3, 5, 7, 9, 11, 13, 15
```

`series_length` defaults to `1`. The server only matches players who request
the same board size and the same series length.

Clients may include `model_name` to display a non-secret player label in
`/slots` and `/overview`:

```text
/ws/matchmake?board_size=11&series_length=3&model_name=model_alphazero
```

`/ws/join-slot?slot_id=1`

Joins a specific waiting slot as `player_2`. The joining client inherits the
board size, series length, wins required, and current score rules already set
by `player_1` in that slot.

`/ws/reconnect?slot_id=1&token=<reconnect_token>`

Reconnects a player to a reserved seat after a temporary disconnect. The token
is issued only to that client in the `joined` payload. It is not exposed by
`/slots` or the overview dashboard.

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
    "player": -1,
    "color": "red",
    "board_size": 11,
    "series_length": 3,
    "reconnect_token": "client-private-token",
    "protocol_version": 1
  }
}
```

Store `reconnect_token` client-side for the current match. Treat it like a
short-lived secret: it proves ownership of the reserved seat.

`reconnected`

```json
{
  "type": "reconnected",
  "payload": {
    "slot_id": 1,
    "player": 1,
    "color": "blue",
    "board_size": 11,
    "series_length": 3,
    "protocol_version": 1,
    "slot": {
      "slot_id": 1,
      "state": "full",
      "connected_players": [-1, 1],
      "disconnected_players": [],
      "current_turn": -1,
      "move_count": 8
    }
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
    "players": [-1, 1],
    "first_turn": -1,
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
    "player": -1,
    "q": 3,
    "r": 5,
    "next_turn": 1
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
    "winner": -1,
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
    "winner": -1,
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
- `opponent_reconnected`

### Player IDs

The protocol uses numeric IDs everywhere a player appears:

```text
-1 = player_1 = red  = left-to-right
 1 = player_2 = blue = top-to-bottom
```

New clients should treat `-1` and `1` as the canonical protocol values. The
server still owns identity: clients do not send their player id in `move`
messages, and any extra `player` field in a move payload is ignored.

## Gameplay Rules

- The current `app/config.py` maps `PLAYER_1 = -1` and `PLAYER_2 = 1`.
- `player_1` (`-1`, red) moves first.
- A game is one Hex board.
- A series is best-of `1`, `3`, `5`, `7`, `9`, `11`, `13`, or `15` games
  between the same players.
- The series ends as soon as a player reaches `ceil(series_length / 2)` wins.
- First turn alternates by game number: odd games start with `player_1` (`-1`),
  even games start with `player_2` (`1`).
- Coordinates are `(q, r)`.
- Board access is `board[r][q]`.
- `player_1` (`-1`, red) wins by connecting left to right.
- `player_2` (`1`, blue) wins by connecting top to bottom.
- Neighbors use the axial-like offsets:

```python
(+1, 0), (-1, 0), (0, +1), (0, -1), (+1, -1), (-1, +1)
```

The server rejects moves when:

- The game has not started.
- The game is paused while a disconnected opponent is inside the reconnect
  window.
- The game is already finished.
- It is not the sender's turn.
- Coordinates are outside the board.
- The target cell is occupied.
- The payload is malformed.

## Reconnect Behavior

When a player disconnects, the server keeps the slot, game board, series score,
and seat assignment in memory for `RECONNECT_TIMEOUT_SECONDS` from
`app/config.py`. The remaining player receives `opponent_disconnected` and the
match is paused. During the pause, moves are rejected with
`Game paused for reconnect`.

The disconnected client reconnects with:

```text
ws://127.0.0.1:8000/ws/reconnect?slot_id=1&token=<reconnect_token>
```

If the token is valid and the timeout has not expired, the server sends
`reconnected` with the current public slot snapshot and notifies the opponent
with `opponent_reconnected`. If the timeout expires first, the slot is reset and
the remaining player is notified and closed.

## Clients

The model and GUI clients default to `wss://hexgame.codingdojo.ai`. Use
`--server ws://localhost:8000` only when you are running your own local server.

### Random Client

The reference random client plays uniformly random legal moves. It is useful
for smoke testing matchmaking, gameplay, and win detection.

Run two clients in separate terminals:

```bash
python -m examples.random_client --board-size 11 --seed 1
python -m examples.random_client --board-size 11 --seed 2
```

Useful options:

```bash
python -m examples.random_client \
  --server wss://hexgame.codingdojo.ai \
  --board-size 11 \
  --series-length 3 \
  --seed 42 \
  --move-delay 0.1
```

There is also a helper script:

```bash
bash examples/run_pair.sh
```

### Model Client

`examples/hex_client.py` loads a model module dynamically. The module must
export:

```python
def agent(board, action_set):
    ...
```

The simplest way to add a model is to copy the random model and replace the
logic inside `agent`:

```bash
cp examples/model_random.py examples/model_my_agent.py
```

```python
# examples/model_my_agent.py
from random import choice


def agent(board, action_set):
    # board contains 0, -1, and 1
    # action_set contains legal (row, col) moves
    return choice(list(action_set))
```

After that, run it by passing the filename stem as `--model-name`:

```bash
python -m examples.hex_client --model-name model_my_agent --board-size 7
python -m examples.hex_client_gui --model-name model_my_agent --board-size 7
python -m examples.hex_client --model-name model_my_agent --board-size 7 --server ws://localhost:8000
```

The model-facing board used by the WebSocket clients follows the server
protocol convention:

```text
0  = empty
-1 = red / model player 1
1  = blue / model player 2
```

The `action_set` passed to the model uses `(row, col)` coordinates. The client
converts model output back to the server protocol shape `{q, r}`.
Before sending a move, the client verifies that the model returned an integer
`(row, col)` pair that is present in `action_set`. If a model returns an
occupied cell, an out-of-bounds cell, a scalar, or coordinates in `{q, r}`
order by mistake, the client stops with a clear model move error instead of
sending an illegal move to the server.

Model clients also export a small JSONL replay log by default under
`examples/replays/`. The log records server messages, applied moves, model
choices, rejected moves, terminal events, and board snapshots around model
decisions. Use `--replay-log off` to disable it or `--replay-log path.jsonl` to
choose an explicit export path.

Run two model clients:

```bash
python -m examples.hex_client --model-name model_random --board-size 7 --series-length 1
python -m examples.hex_client --model-name model_first --board-size 7 --series-length 1
```

To keep the same slot after a completed series and wait for another opponent,
add `--keep-slot`:

```bash
python -m examples.hex_client --model-name model_alphazero --board-size 7 --keep-slot
```

To join a specific waiting slot, add `--slot-id`. The client inherits the slot's
board size and series length from the server:

```bash
python -m examples.hex_client --model-name model_random --slot-id 3
```

Available example models include:

- `model_random`
- `model_first`

### Pygame GUI Model Client

`examples/hex_client_gui.py` is the graphical version of the model client. It
opens a pygame window, draws the Hex board, updates stones as server moves
arrive, highlights the last move, shows coordinate labels, displays model,
slot, score, turn, move count, goal sides, and keeps the final board visible
when the series ends. The GUI marks red/player_1 goal sides as left-right and
blue/player_2 goal sides as top-bottom.

Run it with:

```bash
python -m examples.hex_client_gui \
  --model-name model_random \
  --server wss://hexgame.codingdojo.ai \
  --board-size 7 \
  --series-length 3 \
  --seed 42 \
  --move-delay 0.1 \
  --replay-log auto
```

Close the GUI with `Esc`, `Q`, or the window close button.

To play as a human from the GUI, use `--model-name human`. When it is your
turn, click an empty Hex cell to send the move:

```bash
python -m examples.hex_client_gui --model-name human --board-size 7
```

To join a specific waiting slot from the GUI, add `--slot-id`. The GUI ignores
its local `--board-size` and `--series-length` for gameplay after joining and
uses the settings reported by the server:

```bash
python -m examples.hex_client_gui --model-name human --slot-id 3
```

To keep the same slot after a completed series and wait for another opponent,
add `--keep-slot`. The server resets the series score, keeps the player as
`player_1` in that slot, and moves the slot back to `waiting`:

```bash
python -m examples.hex_client_gui --model-name human --board-size 7 --keep-slot
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
  redis_slots.py         Optional Redis-backed SlotManager
  database.py            SQLAlchemy ORM models and completed-series repository
  game.py                Move validation and win detection
  websocket_manager.py   WebSocket receive loop and gameplay handling
  static/overview/       Built Vite dashboard

frontend/
  src/                   Vite React overview source
  package.json           Frontend scripts and dependencies

examples/
  random_client.py       Simple random WebSocket client
  hex_client.py          Model-driven WebSocket client
  hex_client_gui.py      Pygame model client with graphical board output
  hex_engine.py          Local Hex engine used by ML models
  model_*.py             Example model agents
  setup_mcts.py          Optional C++ MCTS extension build script
  run_pair.sh            Launches two random clients

tests/
  test_*.py              Unit and integration tests
```

## Operational Notes

- The default `memory` backend is single-process only.
- Use `HEX_STATE_BACKEND=redis` before running multiple Uvicorn workers. Redis
  stores shared slot/game/session state, while WebSocket connections remain
  attached to the worker that accepted them.
- `/overview` is an operational/debug dashboard. Protect or disable it before
  exposing this service beyond a trusted local network.
- On disconnect, the slot is held for the reconnect timeout. Clients using
  `--keep-slot` can keep a slot after a finished series or after an opponent
  disconnects.

## Troubleshooting

### `/`, `/docs`, or `/overview` is blank

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

With the memory backend, restart the server. With Redis, inspect or clear keys
under `HEX_REDIS_KEY_PREFIX` if you intentionally want to reset persisted slot
state.
