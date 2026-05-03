from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Integer, String, create_engine
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

    async def close(self) -> None:
        self.engine.dispose()

    async def record_completed_series(self, slot_snapshot: dict[str, Any]) -> None:
        series_winner = slot_snapshot.get("series_winner")
        if series_winner is None:
            return

        player_models = slot_snapshot.get("player_models") or {}
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
            final_board=slot_snapshot.get("board"),
            slot_snapshot=slot_snapshot,
            completed_at=datetime.now(timezone.utc),
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
