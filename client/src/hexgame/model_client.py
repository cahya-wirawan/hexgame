from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import random
from typing import Any
from urllib.parse import urlencode

import websockets
from websockets.exceptions import InvalidStatus, InvalidStatusCode

from hexgame.client_safety import (
    InvalidModelMove,
    MatchReplayLog,
    apply_server_move,
    board_for_model,
    model_move_to_payload,
)

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


def public_query(params: dict[str, object | None]) -> str:
    return urlencode({key: value for key, value in params.items() if value is not None})


def load_model(model_name: str):
    """Resolve ``--model-name`` to a loaded Python module exposing ``agent``.

    Resolution order:

      1. If ``model_name`` looks like a file path (contains ``/`` or ends in
         ``.py``), load that file directly with :mod:`importlib.util`. This
         sidesteps ``sys.path`` entirely — handy for the unpackaged
         ``examples/`` models in a repo checkout.
      2. ``hexgame.models.<model_name>`` — the bundled example models.
      3. ``<model_name>`` — a top-level package/module on ``sys.path``.
      4. ``examples.<model_name>`` — convenience for repo checkouts run from
         the project root (e.g. ``--model-name model_dqn`` finds
         ``examples/model_dqn.py``).

    A :class:`ModuleNotFoundError` raised *inside* a resolved module (e.g. a
    missing ``torch`` import in the model file) is **not** silently swallowed
    — it propagates with its original message so the real cause is visible.
    """
    import importlib.util
    import sys
    from pathlib import Path

    # 1. Filesystem path.
    if "/" in model_name or model_name.endswith(".py"):
        path = Path(model_name).expanduser().resolve()
        if not path.is_file():
            raise ModuleNotFoundError(
                f"--model-name {model_name!r}: file not found at {path}"
            )
        # Make sibling imports in the same directory work
        # (e.g. examples/model_dqn_mcts.py does `import model_dqn`,
        # expecting examples/model_dqn.py next to it).
        parent = str(path.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        # Register before exec so the module can be re-entered through its own
        # name (and so sibling imports that loop back resolve to this object).
        sys.modules[path.stem] = module
        try:
            spec.loader.exec_module(module)  # transitive ImportErrors propagate as-is
        except BaseException:
            sys.modules.pop(path.stem, None)
            raise
        return module

    # 2-4. Importable names, tried in order.
    candidates = (
        f"hexgame.models.{model_name}",
        model_name,
        f"examples.{model_name}",
    )
    last_not_found: ModuleNotFoundError | None = None
    for candidate in candidates:
        try:
            return importlib.import_module(candidate)
        except ModuleNotFoundError as exc:
            # If `exc.name` matches the candidate or a prefix of it, the
            # candidate itself is missing — fine, try the next one.
            # Otherwise the candidate WAS found but a transitive import
            # failed (e.g. `import torch` inside model_dqn.py); re-raise so
            # the user sees the real error.
            missing = exc.name or ""
            if missing == candidate or candidate.startswith(missing + "."):
                last_not_found = exc
                continue
            raise

    raise ModuleNotFoundError(
        f"No model module found for --model-name {model_name!r}. "
        f"Tried: {', '.join(candidates)}. "
        "For an unpackaged file, pass --model-name path/to/model.py instead."
    ) from last_not_found


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
    slot_id: int | None,
    username: str | None,
    seed: int | None,
    move_delay: float,
    replay_log: str,
    keep_slot: bool,
    reconnect_token: str | None = None,
) -> None:
    model = load_model(model_name)
    agent = getattr(model, "agent")
    replay = MatchReplayLog.create(
        replay_log,
        model_name=model_name,
        board_size=board_size,
        series_length=series_length,
    )

    if reconnect_token is not None:
        if slot_id is None:
            raise SystemExit("--reconnect-token requires --slot-id (the slot the token belongs to).")
        query = public_query({
            "slot_id": slot_id,
            "token": reconnect_token,
        })
        uri = f"{server.rstrip('/')}/ws/reconnect?{query}"
    elif slot_id is None:
        query = public_query({
            "board_size": board_size,
            "series_length": series_length,
            "model_name": model_name,
            "username": username,
        })
        uri = f"{server.rstrip('/')}/ws/matchmake?{query}"
    else:
        query = public_query({
            "slot_id": slot_id,
            "model_name": model_name,
            "username": username,
        })
        uri = f"{server.rstrip('/')}/ws/join-slot?{query}"
    player_id: int | None = None
    current_turn: int | None = None
    board: list[list[int | None]] = [[0 for _ in range(board_size)] for _ in range(board_size)]
    pending_move = False
    replay.record(
        "client_start",
        model_name=model_name,
        username=username,
        server=server,
        board_size=board_size,
        series_length=series_length,
        requested_slot_id=slot_id,
        seed=seed,
        move_delay=move_delay,
        keep_slot=keep_slot,
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
                if message_type == "joined":
                    _log_payload = {k: v for k, v in payload.items() if k != "reconnect_token"}
                else:
                    _log_payload = payload
                replay.record("server_message", message_type=message_type, payload=_log_payload)

                if message_type == "joined":
                    player_id = payload["player"]
                    server_board_size = payload.get("board_size", board_size)
                    if server_board_size != board_size:
                        board_size = server_board_size
                        board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                    series_length = payload.get("series_length", series_length)
                    # Surface the reconnect token so the user can copy it for a
                    # future `hexgame play --slot-id N --reconnect-token TOKEN`.
                    issued_token = payload.get("reconnect_token")
                    if issued_token:
                        print(
                            f"reconnect: slot {payload.get('slot_id')} token {issued_token}",
                            flush=True,
                        )
                    replay.record(
                        "joined",
                        player=player_id,
                        slot_id=payload.get("slot_id"),
                        color=payload.get("color"),
                        board_size=board_size,
                        series_length=series_length,
                    )
                elif message_type == "waiting_for_opponent":
                    current_turn = None
                    pending_move = False
                elif message_type == "slot_kept":
                    player_id = payload["player"]
                    server_board_size = payload.get("board_size", board_size)
                    if server_board_size != board_size:
                        board_size = server_board_size
                    series_length = payload.get("series_length", series_length)
                    board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                    current_turn = None
                    pending_move = False
                    replay.record("slot_kept", payload=payload)
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
                    if keep_slot:
                        pending_move = True
                        replay.record("client_send", message_type="keep_slot", payload={})
                        await websocket.send(json.dumps({"type": "keep_slot", "payload": {}}))
                        continue
                    return
                elif message_type == "opponent_disconnected":
                    if keep_slot:
                        current_turn = None
                        pending_move = True
                        replay.record("client_send", message_type="keep_slot", payload={"reason": "opponent_disconnected"})
                        await websocket.send(json.dumps({"type": "keep_slot", "payload": {}}))
                        continue
                    return
                elif message_type in {"opponent_left_slot", "error"}:
                    return

                if player_id is not None and current_turn == player_id and not pending_move:
                    cells = empty_cells(board)
                    if not cells:
                        return
                    await asyncio.sleep(move_delay)
                    try:
                        model_board = board_for_model(board, model)
                        raw_move = agent(model_board, cells)
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
                        model_board=model_board,
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="hexgame play", description="Model-driven Hex client.")
    parser.add_argument("--server", default="wss://hexgame.codingdojo.ai")
    parser.add_argument("--board-size", type=int, default=11)
    parser.add_argument("--series-length", type=int, default=1)
    parser.add_argument(
        "--slot-id",
        type=int,
        help="Join a specific waiting slot and inherit its board size and series length.",
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument("--move-delay", type=float, default=0.1)
    parser.add_argument("--model-name", type=str, default="model_random")
    parser.add_argument(
        "--username",
        type=str,
        help="Public username shown as the model owner in slot views. "
             "Defaults to the OS user (getpass.getuser()) if omitted; pass '' to send anonymously.",
    )
    parser.add_argument(
        "--replay-log",
        default="auto",
        help="Path for JSONL replay export, 'auto' for ./replays, or 'off' to disable.",
    )
    parser.add_argument(
        "--keep-slot",
        action="store_true",
        help="After a completed series, keep this connection in the same slot and wait for another match.",
    )
    parser.add_argument(
        "--reconnect-token",
        type=str,
        help="Resume an in-progress match via /ws/reconnect. Requires --slot-id. "
             "The token is printed to stdout (and recorded in the replay log) on `joined` "
             "the first time you connect.",
    )
    args = parser.parse_args(argv)
    if args.username is None:
        args.username = _default_username()
    asyncio.run(
        run(
            args.model_name,
            args.server,
            args.board_size,
            args.series_length,
            args.slot_id,
            args.username,
            args.seed,
            args.move_delay,
            args.replay_log,
            args.keep_slot,
            args.reconnect_token,
        )
    )


def _default_username() -> str | None:
    """Best-effort OS username, used when ``--username`` isn't supplied.

    Uses :func:`getpass.getuser`, which consults ``$LOGNAME``/``$USER``/``$USERNAME``
    and falls back to the password database. Returns ``None`` if even that fails
    (rare — e.g. no controlling terminal and no env vars set).
    """
    import getpass

    try:
        return getpass.getuser() or None
    except Exception:
        return None


if __name__ == "__main__":
    main()
