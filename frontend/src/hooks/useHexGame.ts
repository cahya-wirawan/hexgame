import { useCallback, useEffect, useRef, useState } from "react";

export type GamePhase = "lobby" | "waiting" | "playing" | "game_over" | "series_over" | "error";

export type GameState = {
  phase: GamePhase;
  myPlayer: number | null;
  board: number[][] | null;
  boardSize: number;
  currentTurn: number | null;
  winner: number | null;
  seriesWinner: number | null;
  player1Wins: number;
  player2Wins: number;
  seriesLength: number;
  winsRequired: number;
  currentGame: number;
  playerModels: Record<string, string>;
  playerUsernames: Record<string, string>;
  slotId: number | null;
  errorMessage: string | null;
  reconnectToken: string | null;
};

const INITIAL: GameState = {
  phase: "lobby",
  myPlayer: null,
  board: null,
  boardSize: 7,
  currentTurn: null,
  winner: null,
  seriesWinner: null,
  player1Wins: 0,
  player2Wins: 0,
  seriesLength: 1,
  winsRequired: 1,
  currentGame: 1,
  playerModels: {},
  playerUsernames: {},
  slotId: null,
  errorMessage: null,
  reconnectToken: null,
};

function wsBase() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
}

type SetState = React.Dispatch<React.SetStateAction<GameState>>;

function attachHandlers(ws: WebSocket, wsRef: React.MutableRefObject<WebSocket | null>, setState: SetState) {
  wsRef.current = ws;

  ws.onmessage = (ev: MessageEvent) => {
    const { type, payload: p } = JSON.parse(ev.data as string) as {
      type: string;
      payload: Record<string, unknown>;
    };

    switch (type) {
      case "joined":
        sessionStorage.setItem("hex_slot_id", String(p.slot_id));
        sessionStorage.setItem("hex_token", String(p.reconnect_token));
        setState((s) => ({
          ...s,
          myPlayer: p.player as number,
          slotId: p.slot_id as number,
          reconnectToken: p.reconnect_token as string,
          boardSize: p.board_size as number,
          seriesLength: p.series_length as number,
        }));
        break;

      case "waiting_for_opponent":
        setState((s) => ({ ...s, phase: "waiting" }));
        break;

      case "game_start": {
        const n = p.board_size as number;
        setState((s) => ({
          ...s,
          phase: "playing",
          board: Array.from({ length: n }, () => Array<number>(n).fill(0)),
          boardSize: n,
          currentTurn: p.first_turn as number,
          winner: null,
          player1Wins: p.player_1_wins as number,
          player2Wins: p.player_2_wins as number,
          seriesLength: p.series_length as number,
          winsRequired: p.wins_required as number,
          currentGame: p.current_game_number as number,
          playerModels: ((p.player_models ?? {}) as Record<string, string>),
          playerUsernames: ((p.player_usernames ?? {}) as Record<string, string>),
          errorMessage: null,
        }));
        break;
      }

      case "move":
        setState((s) => {
          if (!s.board) return s;
          const board = s.board.map((row) => [...row]);
          board[p.r as number][p.q as number] = p.player as number;
          return { ...s, board, currentTurn: (p.next_turn as number | null) };
        });
        break;

      case "game_over":
        setState((s) => ({ ...s, phase: "game_over", winner: p.winner as number, currentTurn: null }));
        break;

      case "series_update":
        setState((s) => ({
          ...s,
          player1Wins: p.player_1_wins as number,
          player2Wins: p.player_2_wins as number,
          currentGame: p.current_game_number as number,
          winsRequired: p.wins_required as number,
        }));
        break;

      case "series_over":
        sessionStorage.removeItem("hex_slot_id");
        sessionStorage.removeItem("hex_token");
        setState((s) => ({
          ...s,
          phase: "series_over",
          seriesWinner: p.winner as number,
          player1Wins: p.player_1_wins as number,
          player2Wins: p.player_2_wins as number,
        }));
        break;

      case "move_rejected":
        setState((s) => ({ ...s, errorMessage: `Move rejected: ${String(p.reason)}` }));
        break;

      case "error":
        setState((s) => ({ ...s, phase: "error", errorMessage: String(p.message) }));
        break;

      case "reconnected": {
        const slot = p.slot as Record<string, unknown>;
        const n = p.board_size as number;
        const rawBoard = slot.board as (number | null)[][] | null;
        const board = rawBoard
          ? rawBoard.map((row) => row.map((cell) => cell ?? 0))
          : Array.from({ length: n }, () => Array<number>(n).fill(0));
        setState((s) => ({
          ...s,
          phase: slot.winner ? "game_over" : slot.state === "full" ? "playing" : "waiting",
          myPlayer: p.player as number,
          slotId: p.slot_id as number,
          boardSize: n,
          seriesLength: p.series_length as number,
          board,
          currentTurn: (slot.current_turn as number | null) ?? null,
          winner: (slot.winner as number | null) ?? null,
          player1Wins: (slot.player_1_wins as number) ?? 0,
          player2Wins: (slot.player_2_wins as number) ?? 0,
          currentGame: (slot.current_game_number as number) ?? 1,
          playerModels: ((slot.player_models as Record<string, string>) ?? {}),
          playerUsernames: ((slot.player_usernames as Record<string, string>) ?? {}),
          errorMessage: null,
        }));
        break;
      }

      case "opponent_disconnected":
        setState((s) => ({ ...s, errorMessage: "Opponent disconnected — waiting for them to reconnect…" }));
        break;

      case "opponent_reconnected":
        setState((s) => ({ ...s, errorMessage: null }));
        break;
    }
  };

  ws.onerror = () => {
    setState((s) => ({ ...s, phase: "error", errorMessage: "WebSocket connection error" }));
  };

  ws.onclose = () => {
    setState((s) =>
      s.phase === "series_over" || s.phase === "lobby"
        ? s
        : { ...s, errorMessage: s.errorMessage ?? "Connection closed" }
    );
  };
}

export function useHexGame() {
  const [state, setState] = useState<GameState>(INITIAL);
  const wsRef = useRef<WebSocket | null>(null);

  const close = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const join = useCallback(
    (username: string, boardSize: number, seriesLength: number) => {
      close();
      setState({ ...INITIAL, phase: "waiting", boardSize, seriesLength });
      const url = `${wsBase()}/ws/matchmake?board_size=${boardSize}&series_length=${seriesLength}&model_name=human&username=${encodeURIComponent(username)}`;
      attachHandlers(new WebSocket(url), wsRef, setState);
    },
    [close]
  );

  const reconnect = useCallback(
    (slotId: number, token: string) => {
      close();
      setState((s) => ({ ...s, phase: "waiting", errorMessage: null }));
      const url = `${wsBase()}/ws/reconnect?slot_id=${slotId}&token=${encodeURIComponent(token)}`;
      attachHandlers(new WebSocket(url), wsRef, setState);
    },
    [close]
  );

  const sendMove = useCallback((q: number, r: number) => {
    wsRef.current?.send(JSON.stringify({ type: "move", payload: { q, r } }));
  }, []);

  const reset = useCallback(() => {
    close();
    sessionStorage.removeItem("hex_slot_id");
    sessionStorage.removeItem("hex_token");
    setState(INITIAL);
  }, [close]);

  useEffect(() => () => close(), [close]);

  return { state, join, sendMove, reconnect, reset };
}
