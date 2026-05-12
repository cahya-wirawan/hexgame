from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class CompletedSeries(Base):
    __tablename__ = "completed_series"

    id = Column(Integer, primary_key=True)
    slot_id = Column(Integer, nullable=False, index=True)
    board_size = Column(Integer, nullable=False)
    series_length = Column(Integer, nullable=False)
    current_game_number = Column(Integer, nullable=False)
    winner = Column(Integer, nullable=False)
    player_1_wins = Column(Integer, nullable=False)
    player_2_wins = Column(Integer, nullable=False)
    player_1_model = Column(String(80), nullable=True)
    player_2_model = Column(String(80), nullable=True)
    player_1_username = Column(String(80), nullable=True)
    player_2_username = Column(String(80), nullable=True)
    final_board = Column(JSON, nullable=True)
    slot_snapshot = Column(JSON, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=False)


class DatabaseMatchRepository:
    def __init__(self, database_url: str, *, auto_create: bool = True):
        self.database_url = database_url
        self.auto_create = auto_create
        self.engine = create_engine(database_url, future=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    async def initialize(self) -> None:
        if self.auto_create:
            Base.metadata.create_all(self.engine)
            self._ensure_auto_created_columns()

    async def close(self) -> None:
        self.engine.dispose()

    def _ensure_auto_created_columns(self) -> None:
        existing_columns = {
            column["name"]
            for column in inspect(self.engine).get_columns(CompletedSeries.__tablename__)
        }
        expected_columns = {
            "player_1_username": "VARCHAR(80)",
            "player_2_username": "VARCHAR(80)",
        }
        missing_columns = [
            (column_name, column_type)
            for column_name, column_type in expected_columns.items()
            if column_name not in existing_columns
        ]

        if not missing_columns:
            return

        with self.engine.begin() as connection:
            for column_name, column_type in missing_columns:
                connection.execute(
                    text(f"ALTER TABLE {CompletedSeries.__tablename__} ADD COLUMN {column_name} {column_type}")
                )

    async def record_completed_series(self, slot_snapshot: dict[str, Any]) -> None:
        series_winner = slot_snapshot.get("series_winner")
        if series_winner is None:
            return

        player_models = slot_snapshot.get("player_models") or {}
        player_usernames = slot_snapshot.get("player_usernames") or {}
        record = CompletedSeries(
            slot_id=slot_snapshot["slot_id"],
            board_size=slot_snapshot["board_size"],
            series_length=slot_snapshot["series_length"],
            current_game_number=slot_snapshot.get("current_game_number") or 1,
            winner=series_winner,
            player_1_wins=slot_snapshot.get("player_1_wins") or 0,
            player_2_wins=slot_snapshot.get("player_2_wins") or 0,
            player_1_model=player_models.get("-1"),
            player_2_model=player_models.get("1"),
            player_1_username=player_usernames.get("-1"),
            player_2_username=player_usernames.get("1"),
            final_board=slot_snapshot.get("board"),
            slot_snapshot=slot_snapshot,
            completed_at=datetime.now(timezone.utc),
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()

    async def statistics(self) -> dict[str, Any]:
        with self.session_factory() as session:
            records = (
                session.query(CompletedSeries)
                .order_by(CompletedSeries.completed_at.desc(), CompletedSeries.id.desc())
                .all()
            )

        leaderboard: dict[str, dict[str, Any]] = {}
        board_sizes: dict[str, int] = {}
        series_lengths: dict[str, int] = {}
        total_games = 0
        total_model_entries = 0

        def entry_key(model_name: str | None, username: str | None) -> str:
            return f"{model_name or 'unknown'}\n{username or ''}"

        def leaderboard_entry(model_name: str | None, username: str | None) -> dict[str, Any]:
            key = entry_key(model_name, username)
            if key not in leaderboard:
                leaderboard[key] = {
                    "model_name": model_name or "unknown",
                    "username": username,
                    "matches": 0,
                    "wins": 0,
                    "losses": 0,
                    "games_won": 0,
                    "games_lost": 0,
                    "win_rate": 0.0,
                }
            return leaderboard[key]

        for record in records:
            total_games += record.current_game_number
            board_sizes[str(record.board_size)] = board_sizes.get(str(record.board_size), 0) + 1
            series_lengths[str(record.series_length)] = series_lengths.get(str(record.series_length), 0) + 1

            players = [
                {
                    "player": -1,
                    "model_name": record.player_1_model,
                    "username": record.player_1_username,
                    "games_won": record.player_1_wins,
                    "games_lost": record.player_2_wins,
                },
                {
                    "player": 1,
                    "model_name": record.player_2_model,
                    "username": record.player_2_username,
                    "games_won": record.player_2_wins,
                    "games_lost": record.player_1_wins,
                },
            ]

            for player in players:
                total_model_entries += 1
                entry = leaderboard_entry(player["model_name"], player["username"])
                entry["matches"] += 1
                entry["games_won"] += player["games_won"]
                entry["games_lost"] += player["games_lost"]
                if record.winner == player["player"]:
                    entry["wins"] += 1
                else:
                    entry["losses"] += 1

        leaderboard_rows = []
        for entry in leaderboard.values():
            entry["win_rate"] = round(entry["wins"] / entry["matches"], 4) if entry["matches"] else 0.0
            leaderboard_rows.append(entry)

        leaderboard_rows.sort(
            key=lambda entry: (
                entry["wins"],
                entry["win_rate"],
                entry["games_won"] - entry["games_lost"],
                entry["model_name"],
            ),
            reverse=True,
        )

        recent_matches = [
            {
                "id": record.id,
                "slot_id": record.slot_id,
                "board_size": record.board_size,
                "series_length": record.series_length,
                "games_played": record.current_game_number,
                "winner": record.winner,
                "player_1_model": record.player_1_model,
                "player_2_model": record.player_2_model,
                "player_1_username": record.player_1_username,
                "player_2_username": record.player_2_username,
                "player_1_wins": record.player_1_wins,
                "player_2_wins": record.player_2_wins,
                "completed_at": record.completed_at.isoformat(),
            }
            for record in records[:20]
        ]

        return {
            "persistence_enabled": True,
            "totals": {
                "matches": len(records),
                "games": total_games,
                "models": len(leaderboard_rows),
                "model_entries": total_model_entries,
            },
            "leaderboard": leaderboard_rows,
            "board_sizes": board_sizes,
            "series_lengths": series_lengths,
            "recent_matches": recent_matches,
        }
