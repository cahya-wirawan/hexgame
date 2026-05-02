from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import random
from typing import Any

import websockets
from websockets.exceptions import InvalidStatus, InvalidStatusCode

# from .model_random import agent

module_name = "model_random"
function_name = "agent"

module = importlib.import_module(module_name)
agent = getattr(module, function_name)

def empty_cells(board: list[list[int | None]]) -> list[tuple[int, int]]:
    return [
        (r, q)
        for r, row in enumerate(board)
        for q, cell in enumerate(row)
        if cell == 0
    ]


async def run(model_name: str, server: str, board_size: int, series_length: int, seed: int | None, move_delay: float) -> None:
    model = importlib.import_module(model_name)
    agent = getattr(model, "agent")

    uri = f"{server.rstrip('/')}/ws/matchmake?board_size={board_size}&series_length={series_length}"
    player_id: int | None = None
    current_turn: int | None = None
    board: list[list[int | None]] = [[0 for _ in range(board_size)] for _ in range(board_size)]
    pending_move = False

    try:
        async with websockets.connect(uri) as websocket:
            async for raw in websocket:
                message: dict[str, Any] = json.loads(raw)
                message_type = message.get("type")
                payload = message.get("payload", {})
                print(message)

                if message_type == "joined":
                    player_id = payload["player"]
                elif message_type == "game_start":
                    current_turn = payload["first_turn"]
                    board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                    pending_move = False
                elif message_type == "move":
                    q = payload["q"]
                    r = payload["r"]
                    board[r][q] = payload["player"]
                    current_turn = payload.get("next_turn")
                    pending_move = False
                elif message_type == "move_rejected":
                    pending_move = False
                elif message_type == "game_over":
                    current_turn = None
                    pending_move = False
                elif message_type in {"series_over", "opponent_disconnected", "error"}:
                    return

                if player_id is not None and current_turn == player_id and not pending_move:
                    cells = empty_cells(board)
                    if not cells:
                        return
                    await asyncio.sleep(move_delay)
                    row, col  = agent(board, cells)
                    pending_move = True
                    await websocket.send(json.dumps({"type": "move", "payload": {"q": col, "r": row}}))
    except (InvalidStatus, InvalidStatusCode) as exc:
        raise SystemExit(
            f"WebSocket connection rejected by {uri}: {exc}\n"
            "Check that FastAPI is running from this repository and was restarted "
            "after installing requirements.txt, especially uvicorn[standard]/websockets."
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="ws://127.0.0.1:8000")
    parser.add_argument("--board-size", type=int, default=11)
    parser.add_argument("--series-length", type=int, default=1)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--move-delay", type=float, default=0.1)
    parser.add_argument("--model-name", type=str, default="model_random")
    args = parser.parse_args()
    asyncio.run(run(args.model_name, args.server, args.board_size, args.series_length, args.seed, args.move_delay))


if __name__ == "__main__":
    main()
