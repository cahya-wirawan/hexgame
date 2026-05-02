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
    from examples.client_safety import InvalidModelMove, MatchReplayLog, apply_server_move, model_move_to_payload
except ModuleNotFoundError:
    from client_safety import InvalidModelMove, MatchReplayLog, apply_server_move, model_move_to_payload

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


async def run(
    model_name: str,
    server: str,
    board_size: int,
    series_length: int,
    seed: int | None,
    move_delay: float,
    replay_log: str,
) -> None:
    model = importlib.import_module(model_name)
    agent = getattr(model, "agent")
    replay = MatchReplayLog.create(
        replay_log,
        model_name=model_name,
        board_size=board_size,
        series_length=series_length,
    )

    uri = f"{server.rstrip('/')}/ws/matchmake?board_size={board_size}&series_length={series_length}"
    player_id: int | None = None
    current_turn: int | None = None
    board: list[list[int | None]] = [[0 for _ in range(board_size)] for _ in range(board_size)]
    pending_move = False
    replay.record(
        "client_start",
        model_name=model_name,
        server=server,
        board_size=board_size,
        series_length=series_length,
        seed=seed,
        move_delay=move_delay,
    )
    if replay.path is not None:
        print(f"Replay log: {replay.path}")

    try:
        async with websockets.connect(uri) as websocket:
            async for raw in websocket:
                message: dict[str, Any] = json.loads(raw)
                message_type = message.get("type")
                payload = message.get("payload", {})
                print(message)
                replay.record("server_message", message_type=message_type, payload=payload)

                if message_type == "joined":
                    player_id = payload["player"]
                    replay.record("joined", player=player_id, slot_id=payload.get("slot_id"), color=payload.get("color"))
                elif message_type == "game_start":
                    current_turn = payload["first_turn"]
                    board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                    pending_move = False
                    replay.record("game_start", payload=payload)
                elif message_type == "move":
                    q = payload["q"]
                    r = payload["r"]
                    try:
                        apply_server_move(board, q, r, payload["player"])
                    except InvalidModelMove as exc:
                        replay.record("client_state_error", error=str(exc), payload=payload, board=board)
                        print(f"Client state error: {exc}")
                        print_board(board, "Local board before rejecting server message")
                        return
                    current_turn = payload.get("next_turn")
                    pending_move = False
                    replay.record("server_move_applied", q=q, r=r, player=payload["player"], next_turn=current_turn, board=board)
                elif message_type == "move_rejected":
                    pending_move = False
                    replay.record("move_rejected", payload=payload, board=board)
                elif message_type == "game_over":
                    current_turn = None
                    pending_move = False
                    replay.record("game_over", payload=payload, board=board)
                elif message_type == "series_over":
                    winner_id = payload.get("winner")
                    replay.record("series_over", payload=payload, board=board)
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
                        raw_move = agent(board, cells)
                        move_payload = model_move_to_payload(raw_move, cells)
                    except InvalidModelMove as exc:
                        replay.record("model_move_error", error=str(exc), legal_moves=cells, board=board)
                        print(f"Model move error: {exc}")
                        print_board(board, "Board at model error")
                        return
                    replay.record(
                        "model_move",
                        player=player_id,
                        raw_move=raw_move,
                        payload=move_payload,
                        legal_move_count=len(cells),
                        board=board,
                    )
                    pending_move = True
                    replay.record("client_send", message_type="move", payload=move_payload)
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
    parser.add_argument(
        "--replay-log",
        default="auto",
        help="Path for JSONL replay export, 'auto' for examples/replays, or 'off' to disable.",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            args.model_name,
            args.server,
            args.board_size,
            args.series_length,
            args.seed,
            args.move_delay,
            args.replay_log,
        )
    )


if __name__ == "__main__":
    main()
