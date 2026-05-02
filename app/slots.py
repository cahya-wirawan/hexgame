from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from fastapi import WebSocket

from .config import PLAYER_1, PLAYER_2, PLAYER_COLORS
from .models import GameSlot, HexGameState, MatchSeriesState, PlayerConnection, SlotAssignment


class SlotManager:
    def __init__(self, max_slots: int = 5):
        self.slots = {
            slot_id: GameSlot(slot_id=slot_id)
            for slot_id in range(1, max_slots + 1)
        }
        self.lock = asyncio.Lock()

    async def join_slot(
        self,
        websocket: WebSocket,
        board_size: int,
        series_length: int = 1,
        model_name: str | None = None,
    ) -> SlotAssignment | None:
        async with self.lock:
            slot = self._find_waiting_slot(board_size, series_length) or self._find_empty_slot()
            if slot is None:
                return None

            if slot.state == "empty":
                slot.board_size = board_size
                slot.series_length = series_length
                slot.series_state = MatchSeriesState.create(series_length)
                slot.player_1 = PlayerConnection(
                    websocket=websocket,
                    player_id=PLAYER_1,
                    color=PLAYER_COLORS[PLAYER_1],
                    reconnect_token=secrets.token_urlsafe(32),
                    model_name=model_name,
                )
                slot.state = "waiting"
                return self._assignment(slot, PLAYER_1)

            if (
                slot.state == "waiting"
                and slot.board_size == board_size
                and slot.series_length == series_length
                and slot.player_2 is None
            ):
                slot.player_2 = PlayerConnection(
                    websocket=websocket,
                    player_id=PLAYER_2,
                    color=PLAYER_COLORS[PLAYER_2],
                    reconnect_token=secrets.token_urlsafe(32),
                    model_name=model_name,
                )
                slot.state = "full"
                first_turn = slot.series_state.first_turn() if slot.series_state else PLAYER_1
                slot.game_state = HexGameState.create(board_size, first_turn=first_turn)
                return self._assignment(slot, PLAYER_2)

            return None

    async def join_slot_by_id(
        self,
        websocket: WebSocket,
        slot_id: int,
        model_name: str | None = None,
    ) -> tuple[SlotAssignment | None, str | None]:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None:
                return None, "Slot does not exist"
            if slot.state != "waiting" or slot.player_1 is None or slot.board_size is None:
                return None, "Slot is not waiting for an opponent"
            if not slot.player_1.connected:
                return None, "Slot owner is disconnected"
            if slot.player_2 is not None:
                return None, "Slot is already full"

            slot.player_2 = PlayerConnection(
                websocket=websocket,
                player_id=PLAYER_2,
                color=PLAYER_COLORS[PLAYER_2],
                reconnect_token=secrets.token_urlsafe(32),
                model_name=model_name,
            )
            slot.state = "full"
            first_turn = slot.series_state.first_turn() if slot.series_state else PLAYER_1
            slot.game_state = HexGameState.create(slot.board_size, first_turn=first_turn)
            return self._assignment(slot, PLAYER_2), None

    async def get_slot(self, slot_id: int) -> GameSlot | None:
        async with self.lock:
            return self.slots.get(slot_id)

    async def snapshot(self) -> list[dict[str, Any]]:
        async with self.lock:
            return [slot.snapshot() for slot in self.slots.values()]

    async def snapshot_for_slot(self, slot_id: int) -> dict[str, Any] | None:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None:
                return None
            return slot.snapshot()

    async def reconnect_slot(self, websocket: WebSocket, slot_id: int, token: str) -> tuple[SlotAssignment | None, str | None]:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None or slot.state == "empty":
                return None, "Slot is not available for reconnect"

            for connection in (slot.player_1, slot.player_2):
                if connection is None:
                    continue
                if secrets.compare_digest(connection.reconnect_token, token):
                    if connection.connected:
                        return None, "Player is already connected"
                    connection.websocket = websocket
                    connection.connected = True
                    connection.disconnected_at = None
                    return self._assignment(slot, connection.player_id), None

            return None, "Invalid reconnect token"

    async def reset_slot(self, slot_id: int, expected_player_id: int | None = None) -> PlayerConnection | None:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None or slot.state == "empty":
                return None

            if expected_player_id is not None and slot.get_connection(expected_player_id) is None:
                return None

            remaining: PlayerConnection | None = None
            if expected_player_id == PLAYER_1:
                remaining = slot.player_2
            elif expected_player_id == PLAYER_2:
                remaining = slot.player_1

            slot.reset()
            return remaining

    async def mark_disconnected(self, slot_id: int, player_id: int) -> tuple[PlayerConnection | None, str | None]:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None or slot.state == "empty":
                return None, None

            connection = slot.get_connection(player_id)
            if connection is None or not connection.connected:
                return None, None

            connection.connected = False
            connection.websocket = None
            connection.disconnected_at = time.monotonic()
            return slot.opponent_connection(player_id), connection.reconnect_token

    async def reset_if_still_disconnected(
        self,
        slot_id: int,
        player_id: int,
        reconnect_token: str,
    ) -> PlayerConnection | None:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None or slot.state == "empty":
                return None

            connection = slot.get_connection(player_id)
            if (
                connection is None
                or connection.connected
                or not secrets.compare_digest(connection.reconnect_token, reconnect_token)
            ):
                return None

            remaining = slot.opponent_connection(player_id)
            slot.reset()
            return remaining

    async def get_opponent(self, slot_id: int, player_id: int) -> PlayerConnection | None:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None:
                return None
            return slot.opponent_connection(player_id)

    async def apply_authoritative_move(self, slot_id: int, player_id: int, q: int, r: int):
        from .game import apply_move

        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None or slot.game_state is None or slot.state != "full":
                return None, "Game has not started"
            if slot.connected_player_count() < 2:
                return None, "Game paused for reconnect"
            result = apply_move(slot.game_state, player_id, q, r)
            connections = [slot.player_1, slot.player_2]
            return (result, connections), None

    async def record_game_result(self, slot_id: int, winner: int):
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None or slot.series_state is None or slot.board_size is None:
                return None, "Game has not started"

            slot.series_state.record_win(winner)
            connections = [slot.player_1, slot.player_2]
            if slot.series_state.series_winner is not None:
                return (
                    {
                        "series_length": slot.series_state.series_length,
                        "wins_required": slot.series_state.wins_required,
                        "player_1_wins": slot.series_state.player_1_wins,
                        "player_2_wins": slot.series_state.player_2_wins,
                        "current_game_number": slot.series_state.current_game_number,
                        "series_winner": slot.series_state.series_winner,
                        "next_game_started": False,
                        "first_turn": None,
                    },
                    connections,
                ), None

            slot.series_state.current_game_number += 1
            first_turn = slot.series_state.first_turn()
            slot.game_state = HexGameState.create(slot.board_size, first_turn=first_turn)
            return (
                {
                    "series_length": slot.series_state.series_length,
                    "wins_required": slot.series_state.wins_required,
                    "player_1_wins": slot.series_state.player_1_wins,
                    "player_2_wins": slot.series_state.player_2_wins,
                    "current_game_number": slot.series_state.current_game_number,
                    "series_winner": None,
                    "next_game_started": True,
                    "first_turn": first_turn,
                    "board_size": slot.board_size,
                    "slot_id": slot.slot_id,
                },
                connections,
            ), None

    async def connections_for_slot(self, slot_id: int) -> list[PlayerConnection]:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None:
                return []
            return [
                connection
                for connection in (slot.player_1, slot.player_2)
                if connection is not None and connection.connected
            ]

    def _find_waiting_slot(self, board_size: int, series_length: int) -> GameSlot | None:
        for slot in self.slots.values():
            if (
                slot.state == "waiting"
                and slot.board_size == board_size
                and slot.series_length == series_length
                and slot.player_1 is not None
                and slot.player_1.connected
                and slot.player_2 is None
            ):
                return slot
        return None

    def _find_empty_slot(self) -> GameSlot | None:
        for slot in self.slots.values():
            if slot.state == "empty":
                return slot
        return None

    def _assignment(self, slot: GameSlot, player_id: int) -> SlotAssignment:
        connection = slot.get_connection(player_id)
        if connection is None or slot.board_size is None or slot.series_length is None:
            raise RuntimeError("slot assignment requested before player was assigned")
        return SlotAssignment(
            slot_id=slot.slot_id,
            player_id=player_id,
            color=connection.color,
            board_size=slot.board_size,
            series_length=slot.series_length,
            opponent_connected=(
                slot.player_1 is not None
                and slot.player_1.connected
                and slot.player_2 is not None
                and slot.player_2.connected
            ),
            player_1=slot.player_1,
            player_2=slot.player_2,
        )
