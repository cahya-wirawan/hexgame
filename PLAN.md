# Hex Game Server Implementation Plan

## 1. Goal

Build a FastAPI-based Hex game server that manages a fixed number of game slots and bridges real-time communication between two clients playing the same Hex game.

The server should:

- Offer a fixed number of game slots, for example 5 slots.
- Allow clients to request a game with a specific board size.
- Only match two clients together if they requested the same board size.
- Use WebSockets for real-time communication.
- Start with simple message bridging.
- Later become authoritative by validating moves and detecting winners.

The first working milestone should be:

> Two clients requesting the same board size can be paired into the same slot and exchange JSON messages in real time.

---

## 2. High-level architecture

```text
Client A  <-- WebSocket -->  FastAPI Server  <-- WebSocket -->  Client B
                           |
                           | manages slots
                           |
                       Slot 1..5
```

The server has two main responsibilities:

1. **Matchmaking and slot management**
   - Track available slots.
   - Track which slots are empty, waiting, full, or reserved.
   - Match clients only with other clients requesting the same board size.

2. **Real-time message handling**
   - Accept WebSocket connections.
   - Assign players to slots.
   - Forward messages between the two clients in a slot.
   - Optionally validate moves and game state.

---

## 3. Recommended endpoint design

There are two possible designs.

### Option A: HTTP slot request followed by WebSocket connection

The client first asks for a slot:

```http
GET /slots/free?board_size=11
```

The server returns:

```json
{
  "slot_id": 1,
  "board_size": 11,
  "reservation_token": "abc123",
  "websocket_url": "ws://localhost:8000/ws/slots/1?board_size=11&token=abc123"
}
```

Then the client connects:

```text
/ws/slots/1?board_size=11&token=abc123
```

This works, but it requires reservation handling to avoid race conditions.

### Option B: direct WebSocket matchmaking

The client connects directly:

```text
/ws/matchmake?board_size=11
```

The server performs matchmaking during the WebSocket connection itself.

This is simpler and safer because matchmaking and joining happen atomically.

### Recommended choice

Use **Option B** for the first implementation:

```text
/ws/matchmake?board_size=11
```

Keep HTTP endpoints such as `/slots` and `/health` for debugging and monitoring.

---

## 4. Minimum API surface

### HTTP endpoints

```http
GET /health
GET /slots
GET /overview
```

`GET /overview` serves the built Vite overview website showing all current
game slots and game states. It is for local debugging and operations, not for
gameplay. During frontend development, run the Vite dev server instead and let
it call the FastAPI `/slots` API.

Optional, if using reservation-based matchmaking:

```http
GET /slots/free?board_size=11
```

### WebSocket endpoints

Recommended:

```text
/ws/matchmake?board_size=11
```

Optional reservation-based alternative:

```text
/ws/slots/{slot_id}?board_size=11&token=abc123
```

---

## 5. Board size rules

Board size is selected by the client at the beginning of the connection request.

Example:

```text
/ws/matchmake?board_size=11
```

The server must only match clients together when their requested board size is the same.

Allowed board sizes should be explicitly configured.

Example:

```python
ALLOWED_BOARD_SIZES = {7, 9, 11, 13, 19}
```

Validation rules:

```text
- board_size must be present
- board_size must be an integer
- board_size must be in ALLOWED_BOARD_SIZES
```

If the board size is invalid, the server should reject the connection.

Example error:

```json
{
  "type": "error",
  "payload": {
    "message": "Unsupported board size"
  }
}
```

---

## 6. Slot model

Each slot represents one potential Hex game.

```python
from dataclasses import dataclass
from typing import Optional
from fastapi import WebSocket

@dataclass
class PlayerConnection:
    websocket: WebSocket
    player_id: str  # "player_1" or "player_2"
    color: str      # for example "blue" or "red"

@dataclass
class GameSlot:
    slot_id: int
    board_size: Optional[int] = None
    player_1: Optional[PlayerConnection] = None
    player_2: Optional[PlayerConnection] = None
    state: str = "empty"
    game_id: Optional[str] = None
    game_state: Optional["HexGameState"] = None
```

Note: `game_state` is `None` until Phase 4 introduces server-authoritative gameplay.
The §17 slot-reset routine clears all of these fields together.
The slot stores server-owned `PlayerConnection` objects, not client-supplied
identity data. Use `player_1.websocket` or `player_2.websocket` when a helper
needs the underlying WebSocket.
Debug snapshots such as `/slots` must not return raw WebSocket objects; expose
only serializable fields such as `slot_id`, `state`, `board_size`,
`player_count`, and optionally assigned player IDs.

Recommended slot states:

```text
empty
waiting
full
```

If using HTTP reservation flow, add:

```text
reserved
```

State meanings:

```text
empty:
  No board size and no players.

waiting:
  One player is connected. The slot has a board size.

full:
  Two players are connected. The game can start or is already running.

reserved:
  Only needed if using GET /slots/free before WebSocket connection.
  A board size and token are assigned, but no WebSocket has connected yet.
```

Example slot list response:

```json
[
  {
    "slot_id": 1,
    "state": "waiting",
    "board_size": 11,
    "player_count": 1
  },
  {
    "slot_id": 2,
    "state": "waiting",
    "board_size": 13,
    "player_count": 1
  },
  {
    "slot_id": 3,
    "state": "empty",
    "board_size": null,
    "player_count": 0
  }
]
```

---

## 7. Slot manager

Create a slot manager responsible for all slot operations.

Responsibilities:

- Initialize the fixed number of slots.
- Find a waiting slot with matching board size.
- Find an empty slot if no waiting slot exists.
- Add players to slots.
- Remove players from slots.
- Reset slots after games end or after disconnection.

Example structure:

```python
class SlotManager:
    def __init__(self, max_slots: int = 5):
        self.slots = {
            slot_id: GameSlot(slot_id=slot_id)
            for slot_id in range(1, max_slots + 1)
        }
```

Recommended matchmaking strategy:

```text
1. Find a waiting slot with the same board_size.
2. If none exists, find an empty slot.
3. Assign the requested board_size to the empty slot.
4. Add the client as player_1 or player_2.
5. If no slot is available, reject the connection.
```

Pseudo-code:

```python
def find_or_create_slot(board_size: int) -> GameSlot | None:
    # Prefer joining a waiting game with same board size
    for slot in slots.values():
        if slot.state == "waiting" and slot.board_size == board_size:
            return slot

    # Otherwise create a new waiting game in an empty slot
    for slot in slots.values():
        if slot.state == "empty":
            slot.board_size = board_size
            return slot

    return None
```

---

## 8. Concurrency and locking

Because multiple clients can connect at nearly the same time, slot operations must be protected.

Use an `asyncio.Lock` around matchmaking and slot modification.

Example:

```python
import asyncio

class SlotManager:
    def __init__(self, max_slots: int):
        self.slots = {...}
        self.lock = asyncio.Lock()

    async def join_slot(self, websocket: WebSocket, board_size: int) -> "SlotAssignment | None":
        async with self.lock:
            # find matching slot
            # assign player
            # update state
            # return a snapshot describing what to send after releasing lock
            pass
```

This prevents race conditions such as:

```text
- Two clients both taking the same player seat.
- A third client joining a full slot.
- A slot being reset while another client is joining.
```

### Critical: do not send WebSocket messages while holding the lock

The slot lock is global. Awaiting `websocket.send_json(...)` while holding it
will block *all* matchmaking until the send completes — and a slow or
half-closed peer can stall the whole server.

Recommended pattern:

```text
1. Acquire lock.
2. Mutate slot state (assign player, change state).
3. Snapshot the data needed for outgoing messages (slot_id, player_ids,
   board_size, opponent websocket reference).
4. Release lock.
5. Send messages outside the lock.
```

The same rule applies to disconnect cleanup: reset the slot under the lock,
then notify the remaining player after releasing it.

Return a small immutable assignment object from `join_slot()` instead of the
mutable `GameSlot` alone. The receive loop can keep `slot_id` and `player_id`;
send helpers can look up the current slot under the lock when they need fresh
state.

Example shape:

```python
@dataclass(frozen=True)
class SlotAssignment:
    slot_id: int
    player_id: str
    color: str
    board_size: int
    opponent_connected: bool
    player_1: PlayerConnection | None
    player_2: PlayerConnection | None
```

---

## 9. Player assignment

When a client joins a slot:

```text
if slot.player_1 is None:
    assign player_1
elif slot.player_2 is None:
    assign player_2
else:
    reject because slot is full
```

Player metadata should use the `PlayerConnection` dataclass from §6.

Suggested color mapping:

```text
player_1 = blue
player_2 = red
```

The server must not trust the client to decide which player they are.

The server should know which WebSocket belongs to which player.

---

## 10. WebSocket matchmaking flow

Endpoint:

```text
/ws/matchmake?board_size=11
```

Connection flow:

```text
1. Client opens WebSocket connection.
2. Server validates board_size.
3. Server accepts the WebSocket.
4. Server finds a waiting slot with the same board size.
5. If none exists, server finds an empty slot.
6. Server assigns the player to the slot.
7. Server sends a joined message.
8. If only one player is present, server sends waiting_for_opponent.
9. If two players are present, server sends game_start to both players.
10. Server starts listening for messages from the connected client.
```

Example first player flow:

```text
Client A connects to /ws/matchmake?board_size=11
Server finds empty slot 1
Server assigns board_size = 11
Server assigns Client A as player_1
Server sends joined
Server sends waiting_for_opponent
```

Example second player flow:

```text
Client B connects to /ws/matchmake?board_size=11
Server finds waiting slot 1 with board_size 11
Server assigns Client B as player_2
Server sends joined to Client B
Server sends game_start to both clients
```

Example different board size flow:

```text
Client C connects to /ws/matchmake?board_size=13
Server must not put Client C into slot 1 because slot 1 uses board_size 11
Server finds another empty slot or rejects if none is available
```

---

## 11. Shared JSON protocol

Both client and server should use the same JSON message protocol.

Every message should contain:

```json
{
  "type": "message_type",
  "payload": {}
}
```

Use protocol versioning from the beginning.

Example:

```json
{
  "type": "hello",
  "payload": {
    "protocol_version": 1,
    "client_name": "hex-client"
  }
}
```

`payload` is always present, even when empty (`{}`). This keeps parsing
uniform on both sides — no special-casing for "messages without a payload".
Messages that carry no data (`resign`, `ping`) still send `"payload": {}`.

---

## 12. Server-to-client messages

### joined

Sent after a client successfully joins a slot.

```json
{
  "type": "joined",
  "payload": {
    "slot_id": 1,
    "player": "player_1",
    "color": "blue",
    "board_size": 11
  }
}
```

### waiting_for_opponent

Sent when only one player is connected.

```json
{
  "type": "waiting_for_opponent",
  "payload": {
    "slot_id": 1,
    "board_size": 11
  }
}
```

### game_start

Sent to both clients when two matching players are connected.

```json
{
  "type": "game_start",
  "payload": {
    "slot_id": 1,
    "board_size": 11,
    "players": ["player_1", "player_2"],
    "first_turn": "player_1"
  }
}
```

### move

Sent when a move is accepted and broadcast.

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

### move_rejected

Sent when the server rejects a move.

```json
{
  "type": "move_rejected",
  "payload": {
    "reason": "Not your turn"
  }
}
```

### opponent_disconnected

Sent when the other player leaves.

```json
{
  "type": "opponent_disconnected",
  "payload": {
    "message": "Your opponent disconnected"
  }
}
```

### game_over

Sent when the game has ended.

```json
{
  "type": "game_over",
  "payload": {
    "winner": "player_1",
    "reason": "connected_sides"
  }
}
```

### error

Sent when something goes wrong.

```json
{
  "type": "error",
  "payload": {
    "message": "Slot is full"
  }
}
```

### pong

Sent in response to a client `ping`.

```json
{
  "type": "pong",
  "payload": {}
}
```

---

## 13. Client-to-server messages

### hello

Optional initial protocol message.

```json
{
  "type": "hello",
  "payload": {
    "protocol_version": 1,
    "client_name": "hex-client"
  }
}
```

### move

Sent by a client when they want to place a stone.

```json
{
  "type": "move",
  "payload": {
    "q": 3,
    "r": 5
  }
}
```

The client should not include `player` in the move. The server already knows which player sent the message.

### chat

Optional chat message.

```json
{
  "type": "chat",
  "payload": {
    "message": "Good luck!"
  }
}
```

### resign

Sent when a player resigns.

```json
{
  "type": "resign",
  "payload": {}
}
```

### ping

Optional keepalive message.

```json
{
  "type": "ping",
  "payload": {}
}
```

The server should respond with a `pong`:

```json
{
  "type": "pong",
  "payload": {}
}
```

---

## 14. Message bridge behavior

In the first version, the server can act mainly as a bridge.

Basic forwarding:

```text
Client A sends message
Server receives message
Server identifies Client A as player_1
Server forwards message to Client B with sender metadata
```

The server should add trusted metadata:

```json
{
  "type": "move",
  "payload": {
    "player": "player_1",
    "q": 3,
    "r": 5
  }
}
```

Do not blindly forward the original client message if it contains untrusted fields such as `player`.

For Phase 3 bridge mode, forward only whitelisted payload fields for each
message type. For example, `move` forwards only integer `q` and `r` plus the
server-assigned `player`; `chat` forwards only a clipped, sanitized `message`.
Unknown message types should produce `error` rather than being forwarded.

---

## 15. Server-authoritative game state

After the bridge works, make the server authoritative.

Each slot should contain a game state:

```python
@dataclass
class HexGameState:
    board_size: int
    board: list[list[str | None]]   # board[r][q] — outer index is r (row)
    current_turn: str = "player_1"
    winner: str | None = None
```

Board representation:

```text
None       = empty cell
player_1   = player 1 stone
player_2   = player 2 stone
```

Indexing convention (used everywhere in this document):

```text
- Outer index is r (row, 0..board_size-1).
- Inner index is q (column, 0..board_size-1).
- Access cells as board[r][q] — never board[q][r].
- player_1 edges: r == 0 (top), r == board_size - 1 (bottom).
- player_2 edges: q == 0 (left), q == board_size - 1 (right).
```

Example board initialization:

```python
board = [[None for _ in range(board_size)] for _ in range(board_size)]
```

Move validation:

```text
1. Game must have started.
2. There must be no winner yet.
3. It must be the sender's turn.
4. q must be inside the board.
5. r must be inside the board.
6. The target cell must be empty.
```

Coordinate validation:

```python
0 <= q < board_size
0 <= r < board_size
```

After a valid move:

```text
1. Place the stone.
2. Check whether the player has won.
3. If no winner, switch turn.
4. Broadcast accepted move to both clients.
5. If there is a winner, broadcast game_over.
```

---

## 16. Hex win detection

Hex has no draws. A player wins by connecting their two opposite sides.

Recommended convention:

```text
player_1 connects top to bottom
player_2 connects left to right
```

Use BFS or DFS to check connected components.

For a hex grid with coordinates `(q, r)`, neighbors can be represented as:

```python
DIRECTIONS = [
    (+1, 0),
    (-1, 0),
    (0, +1),
    (0, -1),
    (+1, -1),
    (-1, +1),
]
```

Player 1 win check:

```text
1. Start from all player_1 cells on the top edge.
2. Traverse connected player_1 cells.
3. If any connected cell reaches the bottom edge, player_1 wins.
```

Player 2 win check:

```text
1. Start from all player_2 cells on the left edge.
2. Traverse connected player_2 cells.
3. If any connected cell reaches the right edge, player_2 wins.
```

Pseudo-code:

```python
def check_winner(board, board_size, player):
    visited = set()
    stack = []

    if player == "player_1":
        for q in range(board_size):
            if board[0][q] == player:
                stack.append((q, 0))
    else:
        for r in range(board_size):
            if board[r][0] == player:
                stack.append((0, r))

    while stack:
        q, r = stack.pop()
        if (q, r) in visited:
            continue
        visited.add((q, r))

        if player == "player_1" and r == board_size - 1:
            return True
        if player == "player_2" and q == board_size - 1:
            return True

        for dq, dr in DIRECTIONS:
            nq, nr = q + dq, r + dr
            if 0 <= nq < board_size and 0 <= nr < board_size:
                if board[nr][nq] == player:
                    stack.append((nq, nr))

    return False
```

---

## 17. Disconnection handling

### First player disconnects before opponent joins

```text
Slot state: waiting -> empty
Clear board_size
Clear player_1
Clear game state
```

### One player disconnects during active game

For the first version:

```text
1. Notify the remaining player with opponent_disconnected.
2. Close the remaining WebSocket.
3. Reset the slot.
```

Later, add reconnect support.

### Disconnect-during-join race

It is possible for player_1 to disconnect *between* player_2 being assigned
and `game_start` being broadcast. To avoid sending `game_start` to a player
whose opponent has already left:

```text
1. After releasing the lock, attempt the `game_start` sends outside the lock.
2. If sending to player_1 fails, send `opponent_disconnected` to player_2,
   close player_2's socket, and reset the slot.
3. If sending to player_2 fails, notify player_1, close player_1's socket,
   and reset the slot.
```

Equivalently, perform the assignment + send-reference-snapshot atomically
under the lock, but defer the `game_start` send until after the lock is
released, and wrap each `send_json` in a try/except that triggers the
disconnect handler on failure.

### Slot reset behavior

When resetting a slot:

```python
slot.board_size = None
slot.player_1 = None
slot.player_2 = None
slot.state = "empty"
slot.game_id = None
slot.game_state = None
```

Disconnect cleanup should be idempotent. A disconnect handler may run after a
send failure handler has already reset the slot, so `reset_slot(slot_id,
expected_player_id=None)` should tolerate already-empty slots and should avoid
notifying a player about their own cleanup.

---

## 18. Reconnect support for later

Reconnect support is optional and should not be part of the first milestone.

When implemented, add:

```text
- client_id
- reconnect_token
- reconnect timeout
- reserved player seat
```

Example flow:

```text
1. Client joins a game.
2. Server returns reconnect_token.
3. Client temporarily disconnects.
4. Server keeps the player seat reserved for a short time.
5. Client reconnects using slot_id and reconnect_token.
6. Server restores the client to the same player seat.
```

Possible reconnect endpoint:

```text
/ws/reconnect?slot_id=1&token=abc123
```

---

## 19. Suggested project structure

```text
hex-server/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── protocol.py
│   ├── slots.py
│   ├── game.py
│   ├── websocket_manager.py
│   └── static/
│       └── overview/        # built Vite assets, generated
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── ui/          # shadcn/ui components
│   │   ├── lib/
│   │   │   └── utils.ts
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── components.json
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── tests/
│   ├── test_slots.py
│   ├── test_protocol.py
│   ├── test_game.py
│   └── test_websocket.py
│
├── examples/
│   └── random_client.py
│
├── requirements.txt
├── README.md
└── PLAN.md
```

### `main.py`

FastAPI app setup and route registration.

### `config.py`

Configuration values:

```python
MAX_SLOTS = 5
ALLOWED_BOARD_SIZES = {7, 9, 11, 13, 19}
PROTOCOL_VERSION = 1
```

### `models.py`

Dataclasses or Pydantic models:

```text
GameSlot
PlayerConnection
HexGameState
```

### `protocol.py`

Message schemas and helper functions:

```text
parse incoming message
validate message type
create outgoing messages
```

### `slots.py`

Slot manager and matchmaking logic.

### `game.py`

Hex game state, move validation, turn logic, and win detection.

### `websocket_manager.py`

WebSocket receive loop, message forwarding, broadcasting, and disconnect handling.

### `frontend/`

Vite + React + TypeScript website for inspecting all current slots and game
states. Use Tailwind CSS for styling and shadcn/ui for common UI primitives
such as cards, badges, tables, buttons, and tabs.

Recommended frontend setup:

```text
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npx shadcn@latest init
```

Keep the overview app operational and dense: this is a monitoring page, not a
marketing page. Prefer a table or compact slot cards, status badges, and
predictable refresh controls.

### `requirements.txt`

Start with:

```text
fastapi
uvicorn[standard]
pytest
pytest-asyncio
httpx
websockets
```

`httpx` supports Starlette/FastAPI test clients. `websockets` is for the
reference random client in §28.

Frontend dependencies live in `frontend/package.json`, not `requirements.txt`.

---

## 20. FastAPI implementation outline

### App startup

Create one global slot manager for the first version:

```python
slot_manager = SlotManager(max_slots=5)
```

This is acceptable only when running a single process.

Do not run multiple Uvicorn workers with in-memory slots.

### Health endpoint

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

### Slots debug endpoint

```python
@app.get("/slots")
def get_slots():
    return slot_manager.snapshot()
```

The snapshot should include enough data for the overview page:

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
    "move_count": 8
  }
]
```

Before Phase 4, fields such as `current_turn`, `winner`, and `move_count` can
be `null` or omitted because no authoritative game state exists yet.

### Game overview page

Build the overview as a Vite website using React, Tailwind CSS, and shadcn/ui.
FastAPI should serve the compiled frontend in production:

```python
@app.get("/overview")
def overview():
    # Return app/static/overview/index.html from the Vite build.
    # Static assets are served from app/static/overview/assets.
    ...
```

During development, run Vite from `frontend/` and configure it to proxy
`/slots` to the FastAPI server. The built output should be copied or emitted to
`app/static/overview/` before serving via FastAPI.

The page should show:

```text
- One row or panel per slot.
- Slot state: empty, waiting, or full.
- Board size.
- Player occupancy and assigned player IDs.
- Current turn, winner, and move count once Phase 4 exists.
- Optional compact board preview once authoritative board state exists.
- Last updated timestamp.
```

Use shadcn/ui components for the page shell and repeated controls:

```text
- Card or Table for slot summaries.
- Badge for slot state and winner state.
- Button for manual refresh.
- Tabs if separating "Slots", "Active games", and "Finished games" later.
```

Do not expose raw WebSocket objects, reconnect tokens, or other secrets on this
page. If the server is exposed beyond localhost, protect or disable the page.

### WebSocket matchmaking endpoint

FastAPI validates the typed query parameter before normal handler logic. A
missing or non-integer `board_size` may be rejected during the upgrade request,
depending on the test client and server stack. The handler still needs to check
that the parsed value is allowed.

For the value check, prefer accepting the connection so the client gets a
structured error message, then closing with code 1008 (policy violation):

```python
@app.websocket("/ws/matchmake")
async def websocket_matchmake(websocket: WebSocket, board_size: int):
    if board_size not in ALLOWED_BOARD_SIZES:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "payload": {"message": "Unsupported board size"}
        })
        await websocket.close(code=1008)
        return

    await websocket.accept()

    assignment = await slot_manager.join_slot(websocket, board_size)
    if assignment is None:
        await websocket.send_json({
            "type": "error",
            "payload": {"message": "No available slot"}
        })
        await websocket.close()
        return

    # send joined
    # maybe send waiting_for_opponent
    # maybe broadcast game_start
    # enter receive loop
```

---

## 21. WebSocket receive loop

Each connected client needs a receive loop.

Pseudo-code:

```python
try:
    while True:
        message = await websocket.receive_json()
        await handle_client_message(assignment.slot_id, assignment.player_id, message)
except WebSocketDisconnect:
    await handle_disconnect(assignment.slot_id, assignment.player_id)
```

Message handling should:

```text
1. Validate message has a type.
2. Validate payload if needed.
3. For bridge mode, forward message to opponent.
4. For authoritative mode, validate and update game state first.
```

---

## 22. Broadcasting helpers

Each slot should support sending to:

```text
- one player
- the opponent
- both players
```

Example helper behavior:

```python
async def send_to_player(slot, player_id, message):
    connection = get_connection_for_player(slot, player_id)
    websocket = connection.websocket if connection else None
    if websocket:
        await websocket.send_json(message)

async def send_to_opponent(slot, player_id, message):
    opponent_id = "player_2" if player_id == "player_1" else "player_1"
    await send_to_player(slot, opponent_id, message)

async def broadcast(slot, message):
    await send_to_player(slot, "player_1", message)
    await send_to_player(slot, "player_2", message)
```

In production code, wrap send failures and route them through the same
disconnect cleanup path used by `WebSocketDisconnect`. Broadcasting to both
players should attempt both sends and then clean up any failed connections, so
a broken first send does not prevent the second player from receiving a final
`opponent_disconnected` or `game_over` message.

---

## 23. Error handling

Common errors:

```text
Unsupported board size
No available slot
Invalid JSON message
Unknown message type
Move outside board
Cell already occupied
Not your turn
Game has not started
Game already finished
Opponent disconnected
```

Standard error message:

```json
{
  "type": "error",
  "payload": {
    "message": "Invalid message type"
  }
}
```

For user actions such as invalid moves, prefer specific messages:

```json
{
  "type": "move_rejected",
  "payload": {
    "reason": "Cell already occupied"
  }
}
```

### Operational limits

To keep a single-process server resilient against misbehaving or abandoned
clients, enforce these limits early:

```text
- Idle timeout for waiting players:
    A slot in state "waiting" should reset if player_1 does not get an
    opponent within e.g. 5 minutes. Otherwise abandoned slots accumulate.

- Connection heartbeat:
    Either rely on WebSocket ping/pong (Starlette/uvicorn handle it) or
    require client `ping` messages every N seconds. Drop the connection
    if no traffic is seen for 2 * N.

- Maximum incoming message size:
    Reject messages larger than e.g. 4 KB. Hex moves are tiny; large
    payloads are either bugs or abuse.

- Per-connection rate limit:
    Cap messages per second (e.g. 20 msg/s) to bound server work. Excess
    messages can be dropped or the connection closed.

- Chat sanitization:
    If chat is enabled, strip control characters and clip to a fixed
    length before forwarding.
```

These do not need to land in Phase 1, but should exist before the server
is exposed to untrusted clients.

---

## 24. Testing plan

### Unit tests

Test slot logic:

```text
- Empty slot can be assigned a board size.
- Client joins waiting slot with same board size.
- Client does not join waiting slot with different board size.
- Full slot is not joinable.
- Slot resets after disconnect.
```

Test game logic:

```text
- Board initializes with correct size.
- Move inside board is valid.
- Move outside board is rejected.
- Move into occupied cell is rejected.
- Turn alternates correctly.
- Player 1 top-to-bottom win is detected.
- Player 2 left-to-right win is detected.
```

Test protocol:

```text
- Valid message types parse correctly.
- Invalid message types are rejected.
- Missing payload is handled safely.
```

Test overview snapshot/page:

```text
- Vite overview app builds successfully.
- /overview returns the built Vite HTML successfully.
- /slots returns only JSON-serializable, non-secret state.
- Slot rows update from empty -> waiting -> full as clients connect.
- After Phase 4, snapshot includes current_turn, winner, move_count, and
  optionally a compact board representation.
```

### Integration tests

Use FastAPI `TestClient` or `pytest-asyncio` WebSocket tests.

Test cases:

```text
- Two clients with board_size 11 are matched together.
- Client with board_size 13 is not matched into board_size 11 slot.
- Third client is placed into another slot or rejected if no slot exists.
- Messages from player_1 are received by player_2.
- Disconnect resets or closes the slot correctly.
```

### Concurrency tests

The lock in §8 is only useful if it is exercised. Add at least one test that
fires many simultaneous connections at the matchmaker and asserts the
invariants hold:

```text
- Launch 2 * MAX_SLOTS clients concurrently with the same board_size.
  Expect: exactly MAX_SLOTS slots become "full", every slot has exactly
  two distinct websockets, no slot has duplicate player assignments.

- Launch MAX_SLOTS + 1 clients concurrently. Expect: one client receives
  "No available slot" and is closed cleanly.

- Launch player_1 and player_2 for the same slot, immediately disconnect
  player_1, and assert player_2 either receives opponent_disconnected or
  is matched into a fresh slot — never left hanging without game_start.
```

---

## 25. Development phases

### Phase 1: Basic FastAPI server

Implement:

```text
- FastAPI app
- /health endpoint
- /slots endpoint
- Vite + React + Tailwind CSS + shadcn/ui overview app scaffold
- /overview route serving the built overview app
- SlotManager with 5 in-memory slots
- Board size validation
```

Goal:

```text
Server starts and exposes current slot state as JSON and as an overview page.
The overview website can be run with Vite during development and built for
FastAPI to serve.
```

---

### Phase 2: Board-size matchmaking

Implement:

```text
- /ws/matchmake?board_size=...
- Match clients only with same board size
- Assign player_1 and player_2
- Send joined message
- Send waiting_for_opponent message
- Send game_start message
```

Goal:

```text
Two clients with the same board size can join the same slot.
Clients with different board sizes are placed into different slots.
```

---

### Phase 3: Message bridge

Implement:

```text
- WebSocket receive loop
- JSON message validation
- Forward messages to opponent
- Add trusted player metadata
- Handle disconnects
```

Goal:

```text
Two matched clients can exchange realtime JSON messages.
```

---

### Phase 4: Authoritative game state

Implement:

```text
- HexGameState
- Board initialization based on board_size
- Move validation
- Turn tracking
- Accepted/rejected move responses
- Enrich /slots and /overview with current_turn, move_count, winner, and
  compact board state
```

Goal:

```text
Server controls legal moves and turn order.
The overview page shows live authoritative game state for every slot.
```

---

### Phase 5: Hex win detection

Implement:

```text
- BFS or DFS connection detection
- player_1 top-to-bottom win
- player_2 left-to-right win
- game_over broadcast
```

Goal:

```text
Server can determine when a Hex game ends.
```

---

### Phase 6: Reconnect support

Status: implemented.

Implement:

```text
- reconnect_token issued in joined messages
- temporary seat reservation after disconnect
- reconnect timeout with slot reset when the token is not used
- /ws/reconnect endpoint
- public slot snapshots showing connected/disconnected players without tokens
- paused gameplay while one player is disconnected
```

Goal:

```text
Players can recover from temporary network drops.
```

---

### Phase 7: Persistence and scaling

Status: implemented for Redis-backed active match state.

Replace in-memory storage with Redis or another shared store.

Use Redis for:

```text
- active slots: implemented through RedisSlotManager
- game state: implemented through serialized HexGameState
- player sessions: implemented through serialized PlayerConnection metadata
- reconnect tokens: implemented and persisted privately
- pub/sub between server workers: not implemented yet; WebSocket connections remain worker-local
```

Use a database for:

```text
- completed games
- users
- ratings
- match history
```

Database-backed completed match history is not part of the current Phase 7
implementation.

Important:

```text
Do not use multiple Uvicorn workers with only in-memory slot state.
Each worker has separate memory, so matchmaking will break.
```

---

## 26. First milestone acceptance criteria

The first milestone is complete when:

```text
1. Server starts with 5 empty slots.
2. Client A connects with board_size 11.
3. Client A is assigned to a slot as player_1.
4. Client A receives waiting_for_opponent.
5. Client B connects with board_size 11.
6. Client B is assigned to the same slot as player_2.
7. Both clients receive game_start.
8. Client C connects with board_size 13.
9. Client C is not assigned to the board_size 11 slot.
10. Client A and Client B can exchange JSON messages.
11. Disconnecting a client cleans up the slot correctly.
12. Invalid board sizes are rejected with a structured error.
13. A client cannot spoof its `player` identity in forwarded messages.
14. Concurrent connection attempts do not overfill slots or duplicate seats.
15. /overview shows all slots and their current empty/waiting/full state.
```

---

## 27. Recommended first implementation target

Start with this narrow target:

```text
FastAPI server with /ws/matchmake?board_size=11 that pairs two clients with the same board size and forwards messages between them.
```

Do not implement full Hex rules immediately.

Build in this order:

```text
1. Slot model
2. Slot manager
3. WebSocket matchmaking
4. Join/wait/game_start messages
5. Message bridge
6. Disconnect cleanup
7. Server-authoritative move validation
8. Win detection
```

This keeps the project easy to test and avoids mixing matchmaking bugs with game-rule bugs.

---

## 28. Example test client: random-move bot

Ship a small reference client at `examples/random_client.py` whose only
strategy is "pick a uniformly random legal move". It is not meant to play
well — it is meant to be the simplest possible thing that exercises the
full matchmaking + protocol + game loop end to end.

### Purpose

```text
- Smoke test: run two instances locally to verify each phase end to end
  without needing a UI.
- Stress test: launch N pairs concurrently to exercise the lock and the
  per-connection limits from §23.
- Protocol reference: minimal, readable example of the JSON protocol for
  anyone writing a real client.
```

### Behavior

```text
1. Connect to ws://<host>:<port>/ws/matchmake?board_size=<N>.
2. Maintain a local board mirror initialized to all-empty once board_size
   is known.
3. Track own player_id and current_turn from server messages.
4. On game_start (and after every accepted move), if it is this client's
   turn, pick uniformly at random from the empty cells, send a move with
   {q, r}, and wait for the server's response.
5. Apply every accepted move broadcast to the local mirror — both own
   moves and the opponent's.
6. On move_rejected, log the reason and wait for the next server message
   (do not retry blindly — the server may have advanced the turn).
7. Exit cleanly on game_over, opponent_disconnected, or error.
```

The client must not assume it is player_1. It must not send a `player`
field in `move` payloads (§13). It must not pick its next move until the
server has confirmed the previous one — this is what makes random_client
a useful protocol conformance check, not just a fuzzer.

### CLI

```text
python -m examples.random_client \
    --server ws://localhost:8000 \
    --board-size 11 \
    [--seed 42] \
    [--move-delay 0.1]
```

```text
- --seed makes runs reproducible for debugging.
- --move-delay (seconds) inserts a small pause before each move so logs
  are readable when running two clients side by side.
```

### Dependencies

Use the `websockets` library (synchronous-friendly asyncio API) rather
than pulling in a full HTTP client. Add to `requirements.txt`:

```text
websockets
```

### Phase compatibility

```text
- Phase 2: Connects and prints joined / waiting_for_opponent / game_start.
  No moves yet — server is not authoritative.
- Phase 3: Sends a move payload on its turn; the bridge forwards it. The
  client uses its local mirror to avoid picking occupied cells, but the
  server is not yet validating.
- Phase 4+: Behavior above is fully exercised. move_rejected should be
  rare and indicates either a server bug or a client/server mirror drift.
- Phase 5+: Two random clients will eventually produce a game_over —
  useful as the first integration smoke test of win detection.
```

### Helper script

A tiny shell wrapper to launch a pair is convenient:

```bash
# examples/run_pair.sh
python -m examples.random_client --board-size 11 &
python -m examples.random_client --board-size 11 &
wait
```
