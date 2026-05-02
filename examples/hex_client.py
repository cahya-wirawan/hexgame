from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import random
from typing import Any

import websockets
from websockets.exceptions import InvalidStatus, InvalidStatusCode

try:
    from examples.client_safety import InvalidModelMove, apply_server_move, model_move_to_payload
except ModuleNotFoundError:
    from client_safety import InvalidModelMove, apply_server_move, model_move_to_payload

MODEL_TO_COLOR = {
    -1: "red",
    1: "blue",
}

MODEL_TO_PLAYER = {
    -1: "player_1",
    1: "player_2",
}

CELL_SYMBOLS = {
    0: ".",
    -1: "R",
    1: "B",
}

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


def print_board(board: list[list[int | None]], title: str = "Board") -> None:
    size = len(board)
    labels = " ".join(f"{q:>2}" for q in range(size))
    print(f"\n{title}")
    print("Red/player_1 connects left-right; Blue/player_2 connects top-bottom")
    print(f"     {labels}")
    # board = list(map(list, zip(*board)))
    for r, row in enumerate(board):
        indent = " " * r
        cells = " ".join(f"{CELL_SYMBOLS.get(cell if cell is not None else 0, '?'):>2}" for cell in row)
        print(f"{indent}{r:>2}   {cells}")
    print()


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
                    try:
                        apply_server_move(board, q, r, payload["player"])
                    except InvalidModelMove as exc:
                        print(f"Client state error: {exc}")
                        print_board(board, "Local board before rejecting server message")
                        return
                    current_turn = payload.get("next_turn")
                    pending_move = False
                elif message_type == "move_rejected":
                    pending_move = False
                elif message_type == "game_over":
                    current_turn = None
                    pending_move = False
                elif message_type == "series_over":
                    winner_id = payload.get("winner")
                    winner = f"{MODEL_TO_PLAYER.get(winner_id, winner_id)}"
                    winner += f" ({MODEL_TO_COLOR.get(winner_id, 'unknown color')})"
                    print_board(
                        board,
                        (
                            "Final board "
                            f"(winner={winner}, "
                            f"score={payload.get('player_1_wins')}:{payload.get('player_2_wins')})"
                        ),
                    )
                    return
                elif message_type in {"opponent_disconnected", "error"}:
                    return

                if player_id is not None and current_turn == player_id and not pending_move:
                    cells = empty_cells(board)
                    if not cells:
                        return
                    await asyncio.sleep(move_delay)
                    try:
                        move_payload = model_move_to_payload(agent(board, cells), cells)
                    except InvalidModelMove as exc:
                        print(f"Model move error: {exc}")
                        print_board(board, "Board at model error")
                        return
                    pending_move = True
                    await websocket.send(json.dumps({"type": "move", "payload": move_payload}))
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
