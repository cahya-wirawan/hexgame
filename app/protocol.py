from __future__ import annotations

from typing import Any

from .config import PROTOCOL_VERSION

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


def joined(slot_id: int, player_id: str, color: str, board_size: int) -> dict[str, Any]:
    return message(
        "joined",
        {
            "slot_id": slot_id,
            "player": player_id,
            "color": color,
            "board_size": board_size,
            "protocol_version": PROTOCOL_VERSION,
        },
    )


def waiting_for_opponent(slot_id: int, board_size: int) -> dict[str, Any]:
    return message("waiting_for_opponent", {"slot_id": slot_id, "board_size": board_size})


def game_start(slot_id: int, board_size: int) -> dict[str, Any]:
    return message(
        "game_start",
        {
            "slot_id": slot_id,
            "board_size": board_size,
            "players": ["player_1", "player_2"],
            "first_turn": "player_1",
        },
    )


def move(player_id: str, q: int, r: int, next_turn: str | None) -> dict[str, Any]:
    return message("move", {"player": player_id, "q": q, "r": r, "next_turn": next_turn})


def game_over(winner: str, reason: str = "connected_sides") -> dict[str, Any]:
    return message("game_over", {"winner": winner, "reason": reason})


def opponent_disconnected() -> dict[str, Any]:
    return message("opponent_disconnected", {"message": "Your opponent disconnected"})


def pong() -> dict[str, Any]:
    return message("pong")
