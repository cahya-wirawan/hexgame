from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import math
from typing import Any
from urllib.parse import urlencode

import websockets
from websockets.exceptions import InvalidStatus, InvalidStatusCode

try:
    from examples.client_safety import InvalidModelMove, MatchReplayLog, apply_server_move, board_for_model, model_move_to_payload
except ModuleNotFoundError:
    from client_safety import InvalidModelMove, MatchReplayLog, apply_server_move, board_for_model, model_move_to_payload

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
    PANEL_LEFT = 730
    PANEL_TOP = 72
    PANEL_WIDTH = 340

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
        self.clicked_cells: list[tuple[int, int]] = []

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
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                cell = self._mouse_to_cell(event.pos)
                if cell is not None:
                    self.clicked_cells.append(cell)
        return self.running

    def consume_clicked_cell(self) -> tuple[int, int] | None:
        if not self.clicked_cells:
            return None
        return self.clicked_cells.pop(0)

    def _mouse_to_cell(self, position: tuple[int, int]) -> tuple[int, int] | None:
        mouse_x, mouse_y = position
        closest_cell = None
        closest_distance = float("inf")

        for cell, center in self.hex_centers.items():
            x, y = center
            distance = math.hypot(mouse_x - x, mouse_y - y)
            if distance < closest_distance:
                closest_distance = distance
                closest_cell = cell

        if closest_distance <= self.hex_radius:
            return closest_cell
        return None

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
        replay_path: str | None,
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
            replay_path=replay_path,
        )
        self.pygame.display.flip()

    def _draw_goal_edges(self) -> None:
        pygame = self.pygame
        size = self.board_size
        top_left = self.hex_centers[(0, 0)]
        top_right = self.hex_centers[(0, size - 1)]
        bottom_left = self.hex_centers[(size - 1, 0)]
        bottom_right = self.hex_centers[(size - 1, size - 1)]
        pygame.draw.line(self.screen, self.COLORS["edge_blue"], top_left, top_right, 16)
        pygame.draw.line(self.screen, self.COLORS["edge_blue"], bottom_left, bottom_right, 16)
        pygame.draw.line(self.screen, self.COLORS["edge_red"], top_left, bottom_left, 16)
        pygame.draw.line(self.screen, self.COLORS["edge_red"], top_right, bottom_right, 16)

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
        replay_path: str | None,
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
        y = self._draw_status_line("Replay", replay_path or "off", y)
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
        y = self._draw_goal_row("red", "player_1 connects left-right", y)
        y = self._draw_goal_row("blue", "player_2 connects top-bottom", y)
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


async def run(
    model_name: str,
    server: str,
    board_size: int,
    series_length: int,
    slot_id: int | None,
    seed: int | None,
    move_delay: float,
    replay_log: str,
    keep_slot: bool,
) -> None:
    human_mode = model_name.lower() in {"human", "manual", "mouse"}
    model = None if human_mode else importlib.import_module(model_name)
    agent = None if human_mode else getattr(model, "agent")
    player_label = "human" if human_mode else model_name
    replay = MatchReplayLog.create(
        replay_log,
        model_name=player_label,
        board_size=board_size,
        series_length=series_length,
    )
    replay_path = str(replay.path) if replay.path is not None else None

    if slot_id is None:
        query = urlencode({
            'board_size': board_size,
            'series_length': series_length,
            'model_name': player_label,
        })
        uri = f"{server.rstrip('/')}/ws/matchmake?{query}"
    else:
        query = urlencode({
            'slot_id': slot_id,
            'model_name': player_label,
        })
        uri = f"{server.rstrip('/')}/ws/join-slot?{query}"
    player_id: int | None = None
    current_turn: int | None = None
    board: list[list[int | None]] = [[0 for _ in range(board_size)] for _ in range(board_size)]
    pending_move = False
    score = (0, 0)
    current_game_number: int | None = None
    assigned_slot_id: int | None = None
    move_count = 0
    last_move: tuple[int, int] | None = None
    last_move_player: int | None = None
    status = "Connecting"
    replay.record(
        "client_start",
        model_name=player_label,
        server=server,
        board_size=board_size,
        series_length=series_length,
        requested_slot_id=slot_id,
        seed=seed,
        move_delay=move_delay,
        gui=True,
        human_mode=human_mode,
        keep_slot=keep_slot,
    )
    viewer = HexBoardViewer(board_size)
    viewer.draw(
        board,
        status=status,
        player_id=player_id,
        current_turn=current_turn,
        score=score,
        game_number=current_game_number,
        series_length=series_length,
        model_name=player_label,
        slot_id=assigned_slot_id,
        move_count=move_count,
        last_move=last_move,
        last_move_player=last_move_player,
        pending_move=pending_move,
        replay_path=replay_path,
    )

    try:
        async with websockets.connect(uri) as websocket:
            async def send_human_click() -> bool:
                nonlocal pending_move, status
                if not human_mode or player_id is None or current_turn != player_id or pending_move:
                    return False

                clicked_cell = viewer.consume_clicked_cell()
                if clicked_cell is None:
                    return False

                row, col = clicked_cell
                if not (0 <= row < board_size and 0 <= col < board_size) or board[row][col] != 0:
                    status = f"Illegal click: row={row}, col={col}"
                    replay.record("human_illegal_click", row=row, col=col, board=board)
                    return False

                move_payload = {"q": col, "r": row}
                pending_move = True
                status = f"Sent move: row={row}, col={col}"
                replay.record("human_move", player=player_id, payload=move_payload, board=board)
                replay.record("client_send", message_type="move", payload=move_payload)
                await websocket.send(json.dumps({"type": "move", "payload": move_payload}))
                return True

            while viewer.running:
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=1 / viewer.FPS)
                except asyncio.TimeoutError:
                    if not viewer.pump_events():
                        return
                    await send_human_click()
                    viewer.draw(
                        board,
                        status=status,
                        player_id=player_id,
                        current_turn=current_turn,
                        score=score,
                        game_number=current_game_number,
                        series_length=series_length,
                        model_name=player_label,
                        slot_id=assigned_slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
                        replay_path=replay_path,
                    )
                    continue

                if not viewer.pump_events():
                    return

                message: dict[str, Any] = json.loads(raw)
                message_type = message.get("type")
                payload = message.get("payload", {})
                replay.record("server_message", message_type=message_type, payload=payload)

                if message_type == "joined":
                    player_id = payload["player"]
                    assigned_slot_id = payload.get("slot_id")
                    server_board_size = payload.get("board_size", board_size)
                    server_series_length = payload.get("series_length", series_length)
                    if server_board_size != board_size:
                        board_size = server_board_size
                        board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                        viewer.pygame.quit()
                        viewer = HexBoardViewer(board_size)
                    series_length = server_series_length
                    replay.record(
                        "joined",
                        player=player_id,
                        slot_id=assigned_slot_id,
                        color=payload.get("color"),
                        board_size=board_size,
                        series_length=series_length,
                    )
                    status = f"Joined slot {assigned_slot_id}"
                elif message_type == "waiting_for_opponent":
                    current_turn = None
                    pending_move = False
                    status = "Waiting for opponent"
                elif message_type == "slot_kept":
                    player_id = payload["player"]
                    assigned_slot_id = payload.get("slot_id", assigned_slot_id)
                    server_board_size = payload.get("board_size", board_size)
                    if server_board_size != board_size:
                        board_size = server_board_size
                        viewer.pygame.quit()
                        viewer = HexBoardViewer(board_size)
                    series_length = payload.get("series_length", series_length)
                    board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                    current_turn = None
                    score = (0, 0)
                    current_game_number = None
                    move_count = 0
                    last_move = None
                    last_move_player = None
                    pending_move = False
                    replay.record("slot_kept", payload=payload)
                    status = f"Kept slot {assigned_slot_id}"
                elif message_type == "game_start":
                    current_turn = payload["first_turn"]
                    current_game_number = payload.get("current_game_number")
                    score = (payload.get("player_1_wins", score[0]), payload.get("player_2_wins", score[1]))
                    board = [[0 for _ in range(board_size)] for _ in range(board_size)]
                    pending_move = False
                    move_count = 0
                    last_move = None
                    last_move_player = None
                    replay.record("game_start", payload=payload)
                    status = "Game started"
                elif message_type == "move":
                    q = payload["q"]
                    r = payload["r"]
                    try:
                        apply_server_move(board, q, r, payload["player"])
                    except InvalidModelMove as exc:
                        replay.record("client_state_error", error=str(exc), payload=payload, board=board)
                        viewer.draw(
                            board,
                            status=f"Client state error: {exc}",
                            player_id=player_id,
                            current_turn=current_turn,
                            score=score,
                            game_number=current_game_number,
                            series_length=series_length,
                            model_name=player_label,
                            slot_id=assigned_slot_id,
                            move_count=move_count,
                            last_move=last_move,
                            last_move_player=last_move_player,
                            pending_move=pending_move,
                            replay_path=replay_path,
                        )
                        await viewer.wait_until_closed()
                        return
                    current_turn = payload.get("next_turn")
                    pending_move = False
                    move_count += 1
                    last_move = (r, q)
                    last_move_player = payload["player"]
                    replay.record("server_move_applied", q=q, r=r, player=payload["player"], next_turn=current_turn, board=board)
                    status = f"Move: row={r}, col={q}"
                elif message_type == "move_rejected":
                    pending_move = False
                    replay.record("move_rejected", payload=payload, board=board)
                    status = f"Move rejected: {payload.get('reason')}"
                elif message_type == "game_over":
                    current_turn = None
                    pending_move = False
                    replay.record("game_over", payload=payload, board=board)
                    status = f"Game over: {payload.get('winner')} wins"
                elif message_type == "series_update":
                    score = (payload.get("player_1_wins", score[0]), payload.get("player_2_wins", score[1]))
                    current_game_number = payload.get("current_game_number", current_game_number)
                    status = "Series score updated"
                elif message_type == "series_over":
                    score = (payload.get("player_1_wins", score[0]), payload.get("player_2_wins", score[1]))
                    replay.record("series_over", payload=payload, board=board)
                    if keep_slot:
                        current_turn = None
                        pending_move = True
                        status = "Keeping slot"
                        replay.record("client_send", message_type="keep_slot", payload={})
                        await websocket.send(json.dumps({"type": "keep_slot", "payload": {}}))
                        continue
                    viewer.draw(
                        board,
                        status=f"Series over: {MODEL_TO_PLAYER[payload.get('winner')]} wins",
                        player_id=player_id,
                        current_turn=None,
                        score=score,
                        game_number=current_game_number,
                        series_length=series_length,
                        model_name=player_label,
                        slot_id=assigned_slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
                        replay_path=replay_path,
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
                        model_name=player_label,
                        slot_id=assigned_slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
                        replay_path=replay_path,
                    )
                    await viewer.wait_until_closed()
                    return
                elif message_type == "opponent_left_slot":
                    viewer.draw(
                        board,
                        status=payload.get("message", "Opponent left slot"),
                        player_id=player_id,
                        current_turn=None,
                        score=score,
                        game_number=current_game_number,
                        series_length=series_length,
                        model_name=player_label,
                        slot_id=assigned_slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=False,
                        replay_path=replay_path,
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
                        model_name=player_label,
                        slot_id=assigned_slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
                        replay_path=replay_path,
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
                    model_name=player_label,
                    slot_id=assigned_slot_id,
                    move_count=move_count,
                    last_move=last_move,
                    last_move_player=last_move_player,
                    pending_move=pending_move,
                    replay_path=replay_path,
                )

                if human_mode:
                    await send_human_click()
                elif player_id is not None and current_turn == player_id and not pending_move:
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
                        model_name=player_label,
                        slot_id=assigned_slot_id,
                        move_count=move_count,
                        last_move=last_move,
                        last_move_player=last_move_player,
                        pending_move=pending_move,
                        replay_path=replay_path,
                    )
                    await asyncio.sleep(move_delay)
                    if not viewer.pump_events():
                        return
                    try:
                        model_board = board_for_model(board, model)
                        raw_move = agent(model_board, cells)
                        move_payload = model_move_to_payload(raw_move, cells)
                    except InvalidModelMove as exc:
                        replay.record("model_move_error", error=str(exc), legal_moves=cells, board=board)
                        viewer.draw(
                            board,
                            status=f"Model move error: {exc}",
                            player_id=player_id,
                            current_turn=current_turn,
                            score=score,
                            game_number=current_game_number,
                            series_length=series_length,
                            model_name=player_label,
                            slot_id=assigned_slot_id,
                            move_count=move_count,
                            last_move=last_move,
                            last_move_player=last_move_player,
                            pending_move=pending_move,
                            replay_path=replay_path,
                        )
                        await viewer.wait_until_closed()
                        return
                    replay.record(
                        "model_move",
                        player=player_id,
                        raw_move=raw_move,
                        payload=move_payload,
                        legal_move_count=len(cells),
                        board=board,
                        model_board=model_board,
                    )
                    status = f"Sent move: row={move_payload['r']}, col={move_payload['q']}"
                    replay.record("client_send", message_type="move", payload=move_payload)
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
    parser.add_argument(
        "--slot-id",
        type=int,
        help="Join a specific waiting slot and inherit its board size and series length.",
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument("--move-delay", type=float, default=0.1)
    parser.add_argument("--model-name", type=str, default="model_random")
    parser.add_argument(
        "--replay-log",
        default="auto",
        help="Path for JSONL replay export, 'auto' for examples/replays, or 'off' to disable.",
    )
    parser.add_argument(
        "--keep-slot",
        action="store_true",
        help="After a completed series, keep this connection in the same slot and wait for another match.",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            args.model_name,
            args.server,
            args.board_size,
            args.series_length,
            args.slot_id,
            args.seed,
            args.move_delay,
            args.replay_log,
            args.keep_slot,
        )
    )


if __name__ == "__main__":
    main()
