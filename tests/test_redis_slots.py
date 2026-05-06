import asyncio

from app.config import PLAYER_1, PLAYER_2
from app.redis_slots import RedisSlotManager
from app.slots import SlotManager


def run(coro):
    return asyncio.run(coro)


def redis_manager_without_connection(max_slots=1):
    manager = RedisSlotManager.__new__(RedisSlotManager)
    SlotManager.__init__(manager, max_slots=max_slots)
    return manager


def test_redis_slot_serialization_preserves_private_match_state_without_websockets():
    async def scenario():
        manager = redis_manager_without_connection()
        await SlotManager.join_slot(manager, object(), 7, series_length=3, model_name="model_a", username="alice")
        await SlotManager.join_slot(manager, object(), 7, series_length=3, model_name="model_b", username="bob")
        await SlotManager.apply_authoritative_move(manager, 1, PLAYER_1, 0, 0)

        serialized = manager._slot_to_dict(manager.slots[1])

        assert serialized["player_1"]["reconnect_token"]
        assert serialized["player_1"]["model_name"] == "model_a"
        assert serialized["player_1"]["username"] == "alice"
        assert serialized["player_2"]["model_name"] == "model_b"
        assert serialized["player_2"]["username"] == "bob"
        assert "websocket" not in serialized["player_1"]
        assert serialized["game_state"]["board"][0][0] == PLAYER_1
        assert serialized["game_state"]["current_turn"] == PLAYER_2

    run(scenario())


def test_redis_slot_hydration_marks_connections_disconnected_after_restart():
    async def scenario():
        manager = redis_manager_without_connection()
        serialized = {
            "slot_id": 1,
            "board_size": 7,
            "series_length": 1,
            "state": "full",
            "game_id": None,
            "player_1": {
                "player_id": PLAYER_1,
                "color": "red",
                "reconnect_token": "token-1",
                "model_name": "model_a",
                "username": "alice",
                "connected": True,
                "disconnected_at": None,
            },
            "player_2": {
                "player_id": PLAYER_2,
                "color": "blue",
                "reconnect_token": "token-2",
                "model_name": "model_b",
                "username": "bob",
                "connected": True,
                "disconnected_at": None,
            },
            "game_state": {
                "board_size": 7,
                "board": [[0 for _ in range(7)] for _ in range(7)],
                "current_turn": PLAYER_1,
                "winner": None,
                "move_count": 0,
            },
            "series_state": {
                "series_length": 1,
                "wins_required": 1,
                "player_1_wins": 0,
                "player_2_wins": 0,
                "current_game_number": 1,
                "series_winner": None,
            },
        }

        slot = manager._slot_from_dict(
            serialized,
            current_slot=None,
            mark_connections_disconnected=True,
        )

        assert slot.player_1 is not None
        assert slot.player_2 is not None
        assert slot.player_1.connected is False
        assert slot.player_2.connected is False
        assert slot.player_1.reconnect_token == "token-1"
        assert slot.player_2.model_name == "model_b"
        assert slot.player_2.username == "bob"

    run(scenario())
