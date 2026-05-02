from __future__ import annotations

from typing import Any

from .config import PLAYER_1, PLAYER_2, PROTOCOL_VERSION

CLIENT_MESSAGE_TYPES = {"hello", "move", "chat", "resign", "ping"}


def parse_client_message(message: object) -> tuple[str, dict[str, Any]] | str:
    if not isinstance(message, dict):
        return "Invalid JSON message"
    message_type = message.get("type")
    payload = message.get("payload", {})
    if not isinstance(message_type, str):
        return "Missing message type"
    if message_type not in CLIENT_MESSAGE_TYPES:
        return "Unknown message type"
    if not isinstance(payload, dict):
        return "Invalid payload"
    return message_type, payload


def message(message_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": message_type, "payload": payload or {}}


def error(message_text: str) -> dict[str, Any]:
    return message("error", {"message": message_text})


def move_rejected(reason: str) -> dict[str, Any]:
    return message("move_rejected", {"reason": reason})


def joined(
    slot_id: int,
    player_id: int,
    color: str,
    board_size: int,
    series_length: int,
    reconnect_token: str,
) -> dict[str, Any]:
    return message(
        "joined",
        {
            "slot_id": slot_id,
            "player": player_id,
            "color": color,
            "board_size": board_size,
            "series_length": series_length,
            "reconnect_token": reconnect_token,
            "protocol_version": PROTOCOL_VERSION,
        },
    )


def reconnected(
    slot_id: int,
    player_id: int,
    color: str,
    board_size: int,
    series_length: int,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    return message(
        "reconnected",
        {
            "slot_id": slot_id,
            "player": player_id,
            "color": color,
            "board_size": board_size,
            "series_length": series_length,
            "protocol_version": PROTOCOL_VERSION,
            "slot": snapshot,
        },
    )


def waiting_for_opponent(slot_id: int, board_size: int) -> dict[str, Any]:
    return message("waiting_for_opponent", {"slot_id": slot_id, "board_size": board_size})


def game_start(
    slot_id: int,
    board_size: int,
    first_turn: int,
    current_game_number: int,
    series_length: int,
    player_1_wins: int,
    player_2_wins: int,
    wins_required: int,
) -> dict[str, Any]:
    return message(
        "game_start",
        {
            "slot_id": slot_id,
            "board_size": board_size,
            "series_length": series_length,
            "players": [PLAYER_1, PLAYER_2],
            "first_turn": first_turn,
            "current_game_number": current_game_number,
            "player_1_wins": player_1_wins,
            "player_2_wins": player_2_wins,
            "wins_required": wins_required,
        },
    )


def move(player_id: int, q: int, r: int, next_turn: int | None) -> dict[str, Any]:
    return message("move", {"player": player_id, "q": q, "r": r, "next_turn": next_turn})


def game_over(winner: int, reason: str = "connected_sides") -> dict[str, Any]:
    return message("game_over", {"winner": winner, "reason": reason})


def series_update(
    player_1_wins: int,
    player_2_wins: int,
    current_game_number: int,
    wins_required: int,
    series_length: int,
) -> dict[str, Any]:
    return message(
        "series_update",
        {
            "player_1_wins": player_1_wins,
            "player_2_wins": player_2_wins,
            "current_game_number": current_game_number,
            "wins_required": wins_required,
            "series_length": series_length,
        },
    )


def series_over(
    winner: int,
    player_1_wins: int,
    player_2_wins: int,
    wins_required: int,
    series_length: int,
) -> dict[str, Any]:
    return message(
        "series_over",
        {
            "winner": winner,
            "player_1_wins": player_1_wins,
            "player_2_wins": player_2_wins,
            "wins_required": wins_required,
            "series_length": series_length,
        },
    )


def opponent_disconnected(reconnect_timeout_seconds: int, reason: str = "waiting_for_reconnect") -> dict[str, Any]:
    return message(
        "opponent_disconnected",
        {
            "message": "Your opponent disconnected",
            "reason": reason,
            "reconnect_timeout_seconds": reconnect_timeout_seconds,
        },
    )


def opponent_reconnected(player_id: int) -> dict[str, Any]:
    return message("opponent_reconnected", {"player": player_id})


def pong() -> dict[str, Any]:
    return message("pong")
