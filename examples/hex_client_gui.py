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
    from examples.client_safety import InvalidModelMove, apply_server_move, model_move_to_payload
except ModuleNotFoundError:
    from client_safety import InvalidModelMove, apply_server_move, model_move_to_payload

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
    BOARD_TOP = 120
    BOARD_LEFT = 90
    PANEL_LEFT = 760
    PANEL_TOP = 72
    PANEL_WIDTH = 308

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
        "panel": (255, 255, 255),
        "panel_border": (203, 213, 225),
        "highlight": (250, 204, 21),
        "white": (255, 255, 255),
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
        self.tiny_font = pygame.font.SysFont("arial", 14)
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
        model_name: str,
        slot_id: int | None,
        move_count: int,
        last_move: tuple[int, int] | None,
        last_move_player: int | None,
        pending_move: bool,
    ) -> None:
        self.pump_events()
        self.screen.fill(self.COLORS["background"])
        self._draw_goal_edges()
        self._draw_board(board, last_move=last_move)
        self._draw_coordinate_labels()
        self._draw_panel(
            status=status,
            player_id=player_id,
            current_turn=current_turn,
            score=score,
            game_number=game_number,
            series_length=series_length,
            model_name=model_name,
            slot_id=slot_id,
            move_count=move_count,
            last_move=last_move,
            last_move_player=last_move_player,
            pending_move=pending_move,
        )
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

    def _draw_board(self, board: list[list[int | None]], *, last_move: tuple[int, int] | None) -> None:
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
                if last_move == (row, col):
                    pygame.draw.circle(
                        self.screen,
                        self.COLORS["highlight"],
                        (int(x), int(y)),
                        int(self.hex_radius * 0.82),
                        4,
                    )

    def _draw_coordinate_labels(self) -> None:
        for col in range(self.board_size):
            x, y = self.hex_centers[(0, col)]
            self._draw_text(str(col), x - 4, y - self.hex_radius - 28, self.tiny_font, self.COLORS["muted"])
        for row in range(self.board_size):
            x, y = self.hex_centers[(row, 0)]
            self._draw_text(str(row), x - self.hex_radius - 34, y - 8, self.tiny_font, self.COLORS["muted"])

    def _draw_panel(
        self,
        *,
        status: str,
        player_id: int | None,
        current_turn: int | None,
        score: tuple[int, int],
        game_number: int | None,
        series_length: int,
        model_name: str,
        slot_id: int | None,
        move_count: int,
        last_move: tuple[int, int] | None,
        last_move_player: int | None,
        pending_move: bool,
    ) -> None:
        pygame = self.pygame
        panel_rect = pygame.Rect(self.PANEL_LEFT, self.PANEL_TOP, self.PANEL_WIDTH, 610)
        pygame.draw.rect(self.screen, self.COLORS["panel"], panel_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.COLORS["panel_border"], panel_rect, width=1, border_radius=8)

        y = self.PANEL_TOP + 20
        self._draw_text("Hex Client", self.PANEL_LEFT + 18, y, self.font, self.COLORS["text"])
        y += 38
        y = self._draw_status_line("Status", status, y)
        y = self._draw_status_line("Model", model_name, y)
        y = self._draw_status_line("Slot", str(slot_id) if slot_id is not None else "-", y)
        y = self._draw_status_line("Game", f"{game_number if game_number is not None else '-'} / {series_length}", y)
        y = self._draw_status_line("Score", f"{score[0]} : {score[1]}", y)
        y = self._draw_status_line("Moves", str(move_count), y)
        y += 8

        self._draw_text("Players", self.PANEL_LEFT + 18, y, self.small_font, self.COLORS["text"])
        y += 30
        y = self._draw_player_row(-1, "player_1", "red", player_id, current_turn, y)
        y = self._draw_player_row(1, "player_2", "blue", player_id, current_turn, y)
        y += 10

        last_move_text = "-"
        if last_move is not None:
            row, col = last_move
            last_move_text = f"row {row}, col {col}"
            if last_move_player is not None:
                last_move_text += f" by {MODEL_TO_PLAYER[last_move_player]}"
        y = self._draw_status_line("Last move", last_move_text, y)
        y = self._draw_status_line("Thinking", "yes" if pending_move else "no", y)
        y += 12

        self._draw_text("Goal Sides", self.PANEL_LEFT + 18, y, self.small_font, self.COLORS["text"])
        y += 28
        y = self._draw_goal_row("red", "player_1 connects top-bottom", y)
        y = self._draw_goal_row("blue", "player_2 connects left-right", y)
        y += 18
        self._draw_text("Esc or Q closes the window", self.PANEL_LEFT + 18, y, self.small_font, self.COLORS["muted"])

    def _draw_player_row(
        self,
        player_value: int,
        player_name: str,
        color_name: str,
        player_id: int | None,
        current_turn: int | None,
        y: int,
    ) -> int:
        x = self.PANEL_LEFT + 18
        pygame = self.pygame
        pygame.draw.circle(self.screen, self.COLORS[color_name], (x + 10, y + 10), 9)
        badges = []
        if player_id == player_value:
            badges.append("you")
        if current_turn == player_value:
            badges.append("turn")
        suffix = f" ({', '.join(badges)})" if badges else ""
        self._draw_text(f"{player_name} {player_value}{suffix}", x + 30, y, self.small_font, self.COLORS["muted"])
        return y + 28

    def _draw_goal_row(self, color_name: str, label: str, y: int) -> int:
        pygame = self.pygame
        x = self.PANEL_LEFT + 18
        pygame.draw.rect(self.screen, self.COLORS[color_name], pygame.Rect(x, y + 5, 20, 8), border_radius=4)
        self._draw_text(label, x + 30, y, self.tiny_font, self.COLORS["muted"])
        return y + 24

    def _draw_status_line(self, label: str, value: str, y: int) -> int:
        self._draw_text(label, self.PANEL_LEFT + 18, y, self.tiny_font, self.COLORS["muted"])
        self._draw_text(self._truncate(value, 26), self.PANEL_LEFT + 105, y - 2, self.small_font, self.COLORS["text"])
        return y + 28

    def _draw_text(self, text: str, x: float, y: float, font, color: tuple[int, int, int]) -> None:
        self.screen.blit(font.render(text, True, color), (int(x), int(y)))

    def _truncate(self, value: str, max_chars: int) -> str:
        return value if len(value) <= max_chars else value[: max_chars - 1] + "."


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
    slot_id: int | None = None
    move_count = 0
    last_move: tuple[int, int] | None = None
    last_move_player: int | None = None
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
        model_name=model_name,
        slot_id=slot_id,
        move_count=move_count,
        last_move=last_move,
        last_move_player=last_move_player,
        pending_move=pending_move,
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
                    slot_id = payload.get("slot_id")
                    status = f"Joined slot {payload.get('slot_id')}"
                elif message_type == "waiting_for_opponent":
                    status = "Waiting for opponent"
                elif message_type == "game_start":
                    current_turn = payload["first_turn"]
                    current_game_number = payload.get("current_game_number")
                    score = (payload.get("player_1_wins", score[0]), payload.get("player_2_wins", score[1]))
                    board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                    pending_move = False
                    move_count = 0
                    last_move = None
                    last_move_player = None
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
                            model_name=model_name,
                            slot_id=slot_id,
                            move_count=move_count,
                            last_move=last_move,
                            last_move_player=last_move_player,
                            pending_move=pending_move,
                        )
                        await viewer.wait_until_closed()
                        return
                    current_turn = payload.get("next_turn")
                    pending_move = False
                    move_count += 1
                    last_move = (r, q)
                    last_move_player = payload["player"]
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
                        model_name=model_name,
                        slot_id=slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
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
                        model_name=model_name,
                        slot_id=slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
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
                        model_name=model_name,
                        slot_id=slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
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
                    model_name=model_name,
                    slot_id=slot_id,
                    move_count=move_count,
                    last_move=last_move,
                    last_move_player=last_move_player,
                    pending_move=pending_move,
                )

                if player_id is not None and current_turn == player_id and not pending_move:
                    cells = empty_cells(board)
                    if not cells:
                        return
                    pending_move = True
                    status = "Model thinking"
                    viewer.draw(
                        board,
                        status=status,
                        player_id=player_id,
                        current_turn=current_turn,
                        score=score,
                        game_number=current_game_number,
                        series_length=series_length,
                        model_name=model_name,
                        slot_id=slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
                    )
                    await asyncio.sleep(move_delay)
                    if not viewer.pump_events():
                        return
                    try:
                        move_payload = model_move_to_payload(agent(board, cells), cells)
                    except InvalidModelMove as exc:
                        viewer.draw(
                            board,
                            status=f"Model move error: {exc}",
                            player_id=player_id,
                            current_turn=current_turn,
                            score=score,
                            game_number=current_game_number,
                            series_length=series_length,
                            model_name=model_name,
                            slot_id=slot_id,
                            move_count=move_count,
                            last_move=last_move,
                            last_move_player=last_move_player,
                            pending_move=pending_move,
                        )
                        await viewer.wait_until_closed()
                        return
                    status = f"Sent move: row={move_payload['r']}, col={move_payload['q']}"
                    await websocket.send(json.dumps({"type": "move", "payload": move_payload}))
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
