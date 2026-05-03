import asyncio

from app.config import PLAYER_1, PLAYER_2
from app.database import CompletedSeries, DatabaseMatchRepository


def run(coro):
    return asyncio.run(coro)


def completed_snapshot():
    return {
        "slot_id": 1,
        "state": "full",
        "board_size": 7,
        "series_length": 3,
        "player_count": 2,
        "connected_player_count": 2,
        "players": [PLAYER_1, PLAYER_2],
        "player_models": {str(PLAYER_1): "model_a", str(PLAYER_2): "model_b"},
        "connected_players": [PLAYER_1, PLAYER_2],
        "disconnected_players": [],
        "current_turn": None,
        "winner": PLAYER_1,
        "move_count": 13,
        "board": [[PLAYER_1, 0], [PLAYER_2, PLAYER_1]],
        "wins_required": 2,
        "current_game_number": 2,
        "player_1_wins": 2,
        "player_2_wins": 0,
        "series_winner": PLAYER_1,
    }


def test_database_repository_records_completed_series(tmp_path):
    async def scenario():
        repository = DatabaseMatchRepository(f"sqlite:///{tmp_path / 'hex.db'}")
        await repository.initialize()
        await repository.record_completed_series(completed_snapshot())

        with repository.session_factory() as session:
            records = session.query(CompletedSeries).all()

        assert len(records) == 1
        assert records[0].slot_id == 1
        assert records[0].winner == PLAYER_1
        assert records[0].player_1_model == "model_a"
        assert records[0].player_2_model == "model_b"
        assert records[0].final_board == [[PLAYER_1, 0], [PLAYER_2, PLAYER_1]]

        await repository.close()

    run(scenario())


def test_database_repository_ignores_unfinished_series(tmp_path):
    async def scenario():
        repository = DatabaseMatchRepository(f"sqlite:///{tmp_path / 'hex.db'}")
        await repository.initialize()
        snapshot = completed_snapshot()
        snapshot["series_winner"] = None
        await repository.record_completed_series(snapshot)

        with repository.session_factory() as session:
            count = session.query(CompletedSeries).count()

        assert count == 0
        await repository.close()

    run(scenario())
