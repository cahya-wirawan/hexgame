from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import ALLOWED_BOARD_SIZES, MAX_SLOTS
from .protocol import error
from .slots import SlotManager
from .websocket_manager import WebSocketGameManager

BASE_DIR = Path(__file__).resolve().parent
OVERVIEW_DIR = BASE_DIR / "static" / "overview"
OVERVIEW_INDEX = OVERVIEW_DIR / "index.html"

app = FastAPI(title="Hex Game Server")
slot_manager = SlotManager(max_slots=MAX_SLOTS)
websocket_game_manager = WebSocketGameManager(slot_manager)

if (OVERVIEW_DIR / "assets").exists():
    app.mount("/overview/assets", StaticFiles(directory=OVERVIEW_DIR / "assets"), name="overview-assets")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/slots")
async def get_slots():
    return await slot_manager.snapshot()


@app.get("/overview")
def overview():
    if OVERVIEW_INDEX.exists():
        return HTMLResponse(OVERVIEW_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<!doctype html><title>Hex Overview</title><h1>Hex Overview</h1>"
        "<p>Build the frontend to generate app/static/overview/index.html.</p>"
    )


@app.websocket("/ws/matchmake")
async def websocket_matchmake(websocket: WebSocket, board_size: int):
    if board_size not in ALLOWED_BOARD_SIZES:
        await websocket.accept()
        await websocket.send_json(error("Unsupported board size"))
        await websocket.close(code=1008)
        return

    await websocket.accept()
    assignment = await slot_manager.join_slot(websocket, board_size)
    if assignment is None:
        await websocket.send_json(error("No available slot"))
        await websocket.close()
        return

    await websocket_game_manager.start(websocket, assignment)
