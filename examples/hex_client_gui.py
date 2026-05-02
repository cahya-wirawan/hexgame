from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import math
from typing import Any

import websockets
from websockets.exceptions import InvalidStatus, InvalidStatusCode

try:
    from examples.client_safety import InvalidModelMove, apply_server_move, normalize_model_move
except ModuleNotFoundError:
    from client_safety import InvalidModelMove, apply_server_move, normalize_model_move

MODEL_TO_COLOR = {
    -1: "red",
    1: "blue",
}

MODEL_TO_PLAYER = {
    -1: "player_1",
    1: "player_2",
}

def empty_cells(board: list[list[int | None]]) -> list[tuple[int, int]]:
    return [
        (r, q)
        for r, row in enumerate(board)
        for q, cell in enumerate(row)
        if cell == 0
    ]


class HexBoardViewer:
    WIDTH = 1100
    HEIGHT = 780
    FPS = 60
    BOARD_TOP = 110
    BOARD_LEFT = 120

    COLORS = {
        "background": (246, 248, 251),
        "cell": (226, 232, 240),
        "grid": (30, 41, 59),
        "red": (220, 38, 38),
        "blue": (37, 99, 235),
        "text": (15, 23, 42),
        "muted": (71, 85, 105),
        "edge_red": (248, 113, 113),
        "edge_blue": (96, 165, 250),
    }

    def __init__(self, board_size: int):
        try:
            import pygame
        except ImportError as exc:
            raise SystemExit(
                "pygame is required for hex_client_gui.py. Install it with: python -m pip install pygame"
            ) from exc

        self.pygame = pygame
        pygame.init()
        self.screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT))
        pygame.display.set_caption("Hex Client")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 24, bold=True)
        self.small_font = pygame.font.SysFont("arial", 18)
        self.board_size = board_size
        self.hex_radius = min(32, max(16, int(260 / max(1, board_size))))
        self.hex_width = math.sqrt(3) * self.hex_radius
        self.hex_vertical_step = 1.5 * self.hex_radius
        self.hex_centers = self._calculate_hex_centers()
        self.running = True

    def _calculate_hex_centers(self) -> dict[tuple[int, int], tuple[float, float]]:
        centers = {}
        for row in range(self.board_size):
            for col in range(self.board_size):
                x = self.BOARD_LEFT + col * self.hex_width + row * self.hex_width / 2
                y = self.BOARD_TOP + row * self.hex_vertical_step
                centers[(row, col)] = (x, y)
        return centers

    def _hex_corners(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        x, y = center
        return [
            (
                x + self.hex_radius * math.cos(math.radians(60 * index + 30)),
                y + self.hex_radius * math.sin(math.radians(60 * index + 30)),
            )
            for index in range(6)
        ]

    def pump_events(self) -> bool:
        pygame = self.pygame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key in {pygame.K_ESCAPE, pygame.K_q}:
                self.running = False
        return self.running

    async def wait_until_closed(self) -> None:
        while self.running:
            self.pump_events()
            self.clock.tick(self.FPS)
            await asyncio.sleep(1 / self.FPS)
        self.pygame.quit()

    def draw(
        self,
        board: list[list[int | None]],
        *,
        status: str,
        player_id: int | None,
        current_turn: int | None,
        score: tuple[int, int],
        game_number: int | None,
        series_length: int,
    ) -> None:
        self.pump_events()
        self.screen.fill(self.COLORS["background"])
        self._draw_goal_edges()
        self._draw_board(board)
        self._draw_status(status, player_id, current_turn, score, game_number, series_length)
        self.pygame.display.flip()

    def _draw_goal_edges(self) -> None:
        pygame = self.pygame
        size = self.board_size
        top_left = self.hex_centers[(0, 0)]
        top_right = self.hex_centers[(0, size - 1)]
        bottom_left = self.hex_centers[(size - 1, 0)]
        bottom_right = self.hex_centers[(size - 1, size - 1)]
        pygame.draw.line(self.screen, self.COLORS["edge_red"], top_left, top_right, 16)
        pygame.draw.line(self.screen, self.COLORS["edge_red"], bottom_left, bottom_right, 16)
        pygame.draw.line(self.screen, self.COLORS["edge_blue"], top_left, bottom_left, 16)
        pygame.draw.line(self.screen, self.COLORS["edge_blue"], top_right, bottom_right, 16)

    def _draw_board(self, board: list[list[int | None]]) -> None:
        pygame = self.pygame
        for row in range(self.board_size):
            for col in range(self.board_size):
                center = self.hex_centers[(row, col)]
                x, y = center
                corners = self._hex_corners(center)
                pygame.draw.polygon(self.screen, self.COLORS["cell"], corners)
                pygame.draw.polygon(self.screen, self.COLORS["grid"], corners, 2)
                value = board[row][col]
                if value == -1:
                    pygame.draw.circle(self.screen, self.COLORS["red"], (int(x), int(y)), int(self.hex_radius * 0.68))
                elif value == 1:
                    pygame.draw.circle(self.screen, self.COLORS["blue"], (int(x), int(y)), int(self.hex_radius * 0.68))

    def _draw_status(
        self,
        status: str,
        player_id: int | None,
        current_turn: int | None,
        score: tuple[int, int],
        game_number: int | None,
        series_length: int,
    ) -> None:
        lines = [
            "Hex Client",
            status,
            f"You: {MODEL_TO_COLOR.get(player_id, 'not joined')} ({MODEL_TO_PLAYER.get(player_id, 'unknown')})",
            f"Turn: {current_turn if current_turn is not None else 'none'}",
            f"Score: {score[0]} : {score[1]}",
            f"Game: {game_number if game_number is not None else '-'} / {series_length}",
            "Esc or Q: close",
        ]
        y = self.HEIGHT - 190
        for index, line in enumerate(lines):
            font = self.font if index == 0 else self.small_font
            color = self.COLORS["text"] if index < 2 else self.COLORS["muted"]
            self.screen.blit(font.render(line, True, color), (30, y + index * 25))


async def run(model_name: str, server: str, board_size: int, series_length: int, seed: int | None, move_delay: float) -> None:
    model = importlib.import_module(model_name)
    agent = getattr(model, "agent")

    uri = f"{server.rstrip('/')}/ws/matchmake?board_size={board_size}&series_length={series_length}"
    player_id: int | None = None
    current_turn: int | None = None
    board: list[list[int | None]] = [[0 for _ in range(board_size)] for _ in range(board_size)]
    pending_move = False
    score = (0, 0)
    current_game_number: int | None = None
    status = "Connecting"
    viewer = HexBoardViewer(board_size)
    viewer.draw(
        board,
        status=status,
        player_id=player_id,
        current_turn=current_turn,
        score=score,
        game_number=current_game_number,
        series_length=series_length,
    )

    try:
        async with websockets.connect(uri) as websocket:
            async for raw in websocket:
                if not viewer.pump_events():
                    return

                message: dict[str, Any] = json.loads(raw)
                message_type = message.get("type")
                payload = message.get("payload", {})

                if message_type == "joined":
                    player_id = payload["player"]
                    status = f"Joined slot {payload.get('slot_id')}"
                elif message_type == "waiting_for_opponent":
                    status = "Waiting for opponent"
                elif message_type == "game_start":
                    current_turn = payload["first_turn"]
                    current_game_number = payload.get("current_game_number")
                    score = (payload.get("player_1_wins", score[0]), payload.get("player_2_wins", score[1]))
                    board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                    pending_move = False
                    status = "Game started"
                elif message_type == "move":
                    q = payload["q"]
                    r = payload["r"]
                    try:
                        apply_server_move(board, q, r, payload["player"])
                    except InvalidModelMove as exc:
                        viewer.draw(
                            board,
                            status=f"Client state error: {exc}",
                            player_id=player_id,
                            current_turn=current_turn,
                            score=score,
                            game_number=current_game_number,
                            series_length=series_length,
                        )
                        await viewer.wait_until_closed()
                        return
                    current_turn = payload.get("next_turn")
                    pending_move = False
                    status = f"Move: row={r}, col={q}"
                elif message_type == "move_rejected":
                    pending_move = False
                    status = f"Move rejected: {payload.get('reason')}"
                elif message_type == "game_over":
                    current_turn = None
                    pending_move = False
                    status = f"Game over: {payload.get('winner')} wins"
                elif message_type == "series_update":
                    score = (payload.get("player_1_wins", score[0]), payload.get("player_2_wins", score[1]))
                    current_game_number = payload.get("current_game_number", current_game_number)
                    status = "Series score updated"
                elif message_type == "series_over":
                    score = (payload.get("player_1_wins", score[0]), payload.get("player_2_wins", score[1]))
                    viewer.draw(
                        board,
                        status=f"Series over: {payload.get('winner')} wins",
                        player_id=player_id,
                        current_turn=None,
                        score=score,
                        game_number=current_game_number,
                        series_length=series_length,
                    )
                    await viewer.wait_until_closed()
                    return
                elif message_type == "opponent_disconnected":
                    viewer.draw(
                        board,
                        status="Opponent disconnected",
                        player_id=player_id,
                        current_turn=None,
                        score=score,
                        game_number=current_game_number,
                        series_length=series_length,
                    )
                    await viewer.wait_until_closed()
                    return
                elif message_type == "error":
                    viewer.draw(
                        board,
                        status=f"Error: {payload.get('message')}",
                        player_id=player_id,
                        current_turn=current_turn,
                        score=score,
                        game_number=current_game_number,
                        series_length=series_length,
                    )
                    await viewer.wait_until_closed()
                    return

                viewer.draw(
                    board,
                    status=status,
                    player_id=player_id,
                    current_turn=current_turn,
                    score=score,
                    game_number=current_game_number,
                    series_length=series_length,
                )

                if player_id is not None and current_turn == player_id and not pending_move:
                    cells = empty_cells(board)
                    if not cells:
                        return
                    await asyncio.sleep(move_delay)
                    if not viewer.pump_events():
                        return
                    try:
                        row, col = normalize_model_move(agent(board, cells), cells)
                    except InvalidModelMove as exc:
                        viewer.draw(
                            board,
                            status=f"Model move error: {exc}",
                            player_id=player_id,
                            current_turn=current_turn,
                            score=score,
                            game_number=current_game_number,
                            series_length=series_length,
                        )
                        await viewer.wait_until_closed()
                        return
                    pending_move = True
                    await websocket.send(json.dumps({"type": "move", "payload": {"q": col, "r": row}}))
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
    args = parser.parse_args()
    asyncio.run(run(args.model_name, args.server, args.board_size, args.series_length, args.seed, args.move_delay))


if __name__ == "__main__":
    main()
