from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    ALLOWED_BOARD_SIZES,
    ALLOWED_SERIES_LENGTHS,
    DATABASE_AUTO_CREATE,
    DATABASE_URL,
    MAX_SLOTS,
    PLAYER_1,
    PLAYER_2,
    REDIS_URL,
    STATE_BACKEND,
)
from .protocol import error
from .slots import SlotManager
from .websocket_manager import WebSocketGameManager

BASE_DIR = Path(__file__).resolve().parent
OVERVIEW_DIR = BASE_DIR / "static" / "overview"
OVERVIEW_INDEX = OVERVIEW_DIR / "index.html"

app = FastAPI(
    title="Hex Game Server",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


@app.middleware("http")
async def _add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def create_slot_manager():
    if STATE_BACKEND == "redis":
        from .redis_slots import RedisSlotManager

        return RedisSlotManager(max_slots=MAX_SLOTS, redis_url=REDIS_URL)
    if STATE_BACKEND != "memory":
        raise RuntimeError(f"Unsupported HEX_STATE_BACKEND={STATE_BACKEND!r}")
    return SlotManager(max_slots=MAX_SLOTS)


slot_manager = create_slot_manager()

_ip_slot_count: dict[str, int] = defaultdict(int)
MAX_SLOTS_PER_IP = 2


def create_match_repository():
    if not DATABASE_URL:
        return None
    from .database import DatabaseMatchRepository

    return DatabaseMatchRepository(DATABASE_URL, auto_create=DATABASE_AUTO_CREATE)


match_repository = create_match_repository()
websocket_game_manager = WebSocketGameManager(slot_manager, match_repository=match_repository)

if (OVERVIEW_DIR / "assets").exists():
    app.mount("/overview/assets", StaticFiles(directory=OVERVIEW_DIR / "assets"), name="overview-assets")

MODELS_DIR = BASE_DIR / "static" / "models"
if MODELS_DIR.exists():
    app.mount("/models", StaticFiles(directory=MODELS_DIR), name="models")


@app.on_event("startup")
async def startup():
    initialize = getattr(slot_manager, "initialize", None)
    if initialize is not None:
        await initialize()
    if match_repository is not None:
        await match_repository.initialize()


@app.on_event("shutdown")
async def shutdown():
    close = getattr(slot_manager, "close", None)
    if close is not None:
        await close()
    if match_repository is not None:
        await match_repository.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/slots")
async def get_slots():
    return await slot_manager.snapshot()


@app.websocket("/ws/slots")
async def websocket_slots(websocket: WebSocket):
    await websocket.accept()
    queue = slot_manager.subscribe()
    try:
        await websocket.send_json(await slot_manager.snapshot())
        while True:
            snapshot = await queue.get()
            await websocket.send_json(snapshot)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        slot_manager.unsubscribe(queue)


@app.get("/api/statistics")
async def get_statistics():
    if match_repository is None:
        return {
            "persistence_enabled": False,
            "totals": {"matches": 0, "games": 0, "models": 0, "model_entries": 0},
            "leaderboard": [],
            "board_sizes": {},
            "series_lengths": {},
            "recent_matches": [],
        }
    return await match_repository.statistics()


def frontend_index():
    if OVERVIEW_INDEX.exists():
        return HTMLResponse(OVERVIEW_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<!doctype html><title>Hex Game Server</title><h1>Hex Game Server</h1>"
        "<p>Build the frontend to generate "
        "src/hexgame/server/static/overview/index.html.</p>"
    )


@app.get("/")
def landing_page():
    return frontend_index()


@app.get("/overview")
def overview():
    return frontend_index()


@app.get("/statistics")
def statistics_page():
    return frontend_index()


@app.get("/docs")
def docs():
    return frontend_index()


@app.get("/play")
def play():
    return frontend_index()


def public_client_label(raw_value: Optional[str], *, max_length: int = 80) -> Optional[str]:
    if raw_value is None:
        return None
    cleaned = "".join(ch for ch in raw_value if ch.isprintable()).strip()
    if not cleaned:
        return None
    return cleaned[:max_length]


@app.websocket("/ws/matchmake")
async def websocket_matchmake(
    websocket: WebSocket,
    board_size: int,
    series_length: int = 1,
    model_name: Optional[str] = None,
    username: Optional[str] = None,
    first_player: Optional[int] = None,
):
    if board_size not in ALLOWED_BOARD_SIZES:
        await websocket.accept()
        await websocket.send_json(error("Unsupported board size"))
        await websocket.close(code=1008)
        return
    if series_length not in ALLOWED_SERIES_LENGTHS:
        await websocket.accept()
        await websocket.send_json(error("Unsupported series length"))
        await websocket.close(code=1008)
        return
    if first_player is not None and first_player not in (PLAYER_1, PLAYER_2):
        await websocket.accept()
        await websocket.send_json(error("Invalid first_player value"))
        await websocket.close(code=1008)
        return

    client_ip = websocket.client.host if websocket.client else "unknown"
    if _ip_slot_count[client_ip] >= MAX_SLOTS_PER_IP:
        await websocket.accept()
        await websocket.send_json(error("Too many connections from your IP"))
        await websocket.close(code=1008)
        return

    await websocket.accept()
    _ip_slot_count[client_ip] += 1
    try:
        assignment = await slot_manager.join_slot(
            websocket,
            board_size,
            series_length,
            public_client_label(model_name),
            public_client_label(username),
            first_player=first_player if first_player is not None else PLAYER_1,
        )
        if assignment is None:
            await websocket.send_json(error("No available slot"))
            await websocket.close()
            return

        await websocket_game_manager.start(websocket, assignment)
    finally:
        _ip_slot_count[client_ip] -= 1


@app.websocket("/ws/join-slot")
async def websocket_join_slot(
    websocket: WebSocket,
    slot_id: int,
    model_name: Optional[str] = None,
    username: Optional[str] = None,
):
    await websocket.accept()
    assignment, failure = await slot_manager.join_slot_by_id(
        websocket,
        slot_id,
        public_client_label(model_name),
        public_client_label(username),
    )
    if failure is not None or assignment is None:
        await websocket.send_json(error(failure or "Could not join slot"))
        await websocket.close(code=1008)
        return

    await websocket_game_manager.start(websocket, assignment)


@app.websocket("/ws/reconnect")
async def websocket_reconnect(websocket: WebSocket, slot_id: int, token: str):
    await websocket.accept()
    assignment, failure = await slot_manager.reconnect_slot(websocket, slot_id, token)
    if failure is not None or assignment is None:
        await websocket.send_json(error(failure or "Reconnect failed"))
        await websocket.close(code=1008)
        return

    await websocket_game_manager.start(websocket, assignment, is_reconnect=True)
