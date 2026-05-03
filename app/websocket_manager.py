from __future__ import annotations

import asyncio
from collections.abc import Iterable

from fastapi import WebSocket, WebSocketDisconnect

from .config import PLAYER_1, PLAYER_2, RECONNECT_TIMEOUT_SECONDS
from .game import validate_move_payload
from .models import PlayerConnection, SlotAssignment
from .protocol import (
    error,
    game_over,
    game_start,
    joined,
    message,
    move,
    move_rejected,
    opponent_disconnected,
    opponent_left_slot,
    opponent_reconnected,
    parse_client_message,
    pong,
    reconnected,
    slot_kept,
    series_over,
    series_update,
    waiting_for_opponent,
)
from .slots import SlotManager


class WebSocketGameManager:
    def __init__(self, slot_manager: SlotManager, match_repository=None):
        self.slot_manager = slot_manager
        self.match_repository = match_repository

    async def start(self, websocket: WebSocket, assignment: SlotAssignment, is_reconnect: bool = False) -> None:
        if is_reconnect:
            await self._send_reconnected(websocket, assignment)
        else:
            await websocket.send_json(
                joined(
                    assignment.slot_id,
                    assignment.player_id,
                    assignment.color,
                    assignment.board_size,
                    assignment.series_length,
                    self._reconnect_token(assignment),
                )
            )

        if is_reconnect:
            opponent = await self.slot_manager.get_opponent(assignment.slot_id, assignment.player_id)
            if opponent is not None and opponent.connected:
                await self._safe_send(opponent, opponent_reconnected(assignment.player_id), assignment.slot_id)
            elif not assignment.opponent_connected:
                await websocket.send_json(waiting_for_opponent(assignment.slot_id, assignment.board_size))
        elif assignment.opponent_connected:
            start_message = await self._game_start_message(assignment.slot_id, assignment.board_size)
            await self._broadcast_connections(
                [assignment.player_1, assignment.player_2],
                start_message,
                assignment.slot_id,
            )
        else:
            await websocket.send_json(waiting_for_opponent(assignment.slot_id, assignment.board_size))

        try:
            await self._receive_loop(websocket, assignment)
        except WebSocketDisconnect:
            await self.handle_disconnect(assignment.slot_id, assignment.player_id, assignment.reconnect_token)

    async def _send_reconnected(self, websocket: WebSocket, assignment: SlotAssignment) -> None:
        snapshot = await self.slot_manager.snapshot_for_slot(assignment.slot_id)
        await websocket.send_json(
            reconnected(
                assignment.slot_id,
                assignment.player_id,
                assignment.color,
                assignment.board_size,
                assignment.series_length,
                snapshot or {},
            )
        )

    async def _receive_loop(self, websocket: WebSocket, assignment: SlotAssignment) -> None:
        while True:
            try:
                raw_message = await websocket.receive_json()
            except ValueError:
                await websocket.send_json(error("Invalid JSON message"))
                continue

            parsed = parse_client_message(raw_message)
            if isinstance(parsed, str):
                await websocket.send_json(error(parsed))
                continue

            message_type, payload = parsed
            if message_type == "hello":
                await websocket.send_json(message("hello", {"protocol_version": 1}))
            elif message_type == "ping":
                await websocket.send_json(pong())
            elif message_type == "move":
                await self._handle_move(websocket, assignment, payload)
            elif message_type == "chat":
                await self._handle_chat(assignment, payload)
            elif message_type == "resign":
                await self._handle_resign(assignment)
                return
            elif message_type == "keep_slot":
                kept_assignment = await self._handle_keep_slot(websocket, assignment)
                if kept_assignment is not None:
                    assignment = kept_assignment

    async def _handle_move(self, websocket: WebSocket, assignment: SlotAssignment, payload: dict) -> None:
        coordinates = validate_move_payload(payload)
        if isinstance(coordinates, str):
            await websocket.send_json(move_rejected(coordinates))
            return

        q, r = coordinates
        applied, failure = await self.slot_manager.apply_authoritative_move(
            assignment.slot_id,
            assignment.player_id,
            q,
            r,
        )
        if failure is not None or applied is None:
            await websocket.send_json(move_rejected(failure or "Move rejected"))
            return

        result, connections = applied
        if not result.accepted:
            await websocket.send_json(move_rejected(result.reason or "Move rejected"))
            return

        await self._broadcast_connections(
            connections,
            move(assignment.player_id, q, r, result.next_turn),
            assignment.slot_id,
        )

        if result.winner is not None:
            await self._broadcast_connections(
                connections,
                game_over(result.winner),
                assignment.slot_id,
            )
            series_result, failure = await self.slot_manager.record_game_result(
                assignment.slot_id,
                result.winner,
            )
            if failure is not None or series_result is None:
                return

            state, series_connections = series_result
            await self._broadcast_connections(
                series_connections,
                series_update(
                    state["player_1_wins"],
                    state["player_2_wins"],
                    state["current_game_number"],
                    state["wins_required"],
                    state["series_length"],
                ),
                assignment.slot_id,
            )

            if state["series_winner"] is not None:
                await self._record_completed_series(assignment.slot_id)
                await self._broadcast_connections(
                    series_connections,
                    series_over(
                        state["series_winner"],
                        state["player_1_wins"],
                        state["player_2_wins"],
                        state["wins_required"],
                        state["series_length"],
                    ),
                    assignment.slot_id,
                )
            elif state["next_game_started"]:
                await self._broadcast_connections(
                    series_connections,
                    game_start(
                        state["slot_id"],
                        state["board_size"],
                        state["first_turn"],
                        state["current_game_number"],
                        state["series_length"],
                        state["player_1_wins"],
                        state["player_2_wins"],
                        state["wins_required"],
                    ),
                    assignment.slot_id,
                )

    async def _handle_chat(self, assignment: SlotAssignment, payload: dict) -> None:
        raw_message = payload.get("message", "")
        if not isinstance(raw_message, str):
            return
        sanitized = "".join(ch for ch in raw_message if ch.isprintable())[:500]
        opponent = await self.slot_manager.get_opponent(assignment.slot_id, assignment.player_id)
        if opponent is not None:
            await self._safe_send(
                opponent,
                message("chat", {"player": assignment.player_id, "message": sanitized}),
                assignment.slot_id,
            )

    async def _handle_resign(self, assignment: SlotAssignment) -> None:
        winner = PLAYER_2 if assignment.player_id == PLAYER_1 else PLAYER_1
        connections = await self.slot_manager.connections_for_slot(assignment.slot_id)
        await self._broadcast_connections(connections, game_over(winner, "resignation"), assignment.slot_id)
        await self.handle_disconnect(assignment.slot_id, assignment.player_id, assignment.reconnect_token)

    async def _handle_keep_slot(self, websocket: WebSocket, assignment: SlotAssignment) -> SlotAssignment | None:
        kept, failure = await self.slot_manager.keep_slot_for_next_match(
            assignment.slot_id,
            assignment.player_id,
            assignment.reconnect_token,
        )
        if failure is not None or kept is None:
            await websocket.send_json(error(failure or "Could not keep slot"))
            return None

        kept_assignment, opponent = kept
        await websocket.send_json(
            slot_kept(
                kept_assignment.slot_id,
                kept_assignment.board_size,
                kept_assignment.series_length,
                kept_assignment.reconnect_token,
            )
        )
        await websocket.send_json(waiting_for_opponent(kept_assignment.slot_id, kept_assignment.board_size))

        if opponent is not None and opponent.connected and opponent.websocket is not None:
            try:
                await opponent.websocket.send_json(opponent_left_slot())
                await opponent.websocket.close()
            except RuntimeError:
                pass

        return kept_assignment

    async def _record_completed_series(self, slot_id: int) -> None:
        if self.match_repository is None:
            return
        snapshot = await self.slot_manager.snapshot_for_slot(slot_id)
        if snapshot is None:
            return
        try:
            await self.match_repository.record_completed_series(snapshot)
        except Exception as exc:
            print(f"Failed to record completed series: {exc}")

    async def handle_disconnect(
        self,
        slot_id: int,
        player_id: int,
        reconnect_token: str | None = None,
    ) -> None:
        remaining, reconnect_token = await self.slot_manager.mark_disconnected(slot_id, player_id, reconnect_token)
        if reconnect_token is None:
            return
        if remaining is not None and remaining.connected:
            await self._safe_send(
                remaining,
                opponent_disconnected(RECONNECT_TIMEOUT_SECONDS),
                slot_id,
            )
        asyncio.create_task(self._reset_after_reconnect_timeout(slot_id, player_id, reconnect_token))

    async def _reset_after_reconnect_timeout(self, slot_id: int, player_id: int, reconnect_token: str) -> None:
        await asyncio.sleep(RECONNECT_TIMEOUT_SECONDS)
        remaining = await self.slot_manager.reset_if_still_disconnected(slot_id, player_id, reconnect_token)
        if remaining is None or not remaining.connected:
            return
        if remaining.websocket is None:
            return
        try:
            await remaining.websocket.send_json(
                opponent_disconnected(RECONNECT_TIMEOUT_SECONDS, reason="reconnect_timeout")
            )
            await remaining.websocket.close()
        except RuntimeError:
            pass

    async def _broadcast_connections(
        self,
        connections: Iterable[PlayerConnection | None],
        outbound: dict,
        slot_id: int,
    ) -> None:
        for connection in connections:
            if connection is not None and connection.connected and connection.websocket is not None:
                await self._safe_send(connection, outbound, slot_id)

    async def _safe_send(self, connection: PlayerConnection, outbound: dict, slot_id: int) -> None:
        if not connection.connected or connection.websocket is None:
            return
        try:
            await connection.websocket.send_json(outbound)
        except RuntimeError:
            await self.handle_disconnect(slot_id, connection.player_id, connection.reconnect_token)

    def _reconnect_token(self, assignment: SlotAssignment) -> str:
        return assignment.reconnect_token

    async def _game_start_message(self, slot_id: int, board_size: int) -> dict:
        slot = await self.slot_manager.get_slot(slot_id)
        if slot is None or slot.series_state is None or slot.game_state is None:
            return game_start(slot_id, board_size, PLAYER_1, 1, 1, 0, 0, 1)
        return game_start(
            slot_id,
            board_size,
            slot.game_state.current_turn,
            slot.series_state.current_game_number,
            slot.series_state.series_length,
            slot.series_state.player_1_wins,
            slot.series_state.player_2_wins,
            slot.series_state.wins_required,
        )
