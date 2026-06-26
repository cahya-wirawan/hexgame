import { useCallback, useEffect, useRef, useState } from "react";

export type GamePhase = "lobby" | "waiting" | "playing" | "game_over" | "series_over" | "error";

const BETWEEN_GAME_DELAY_MS = 3000;

type PendingGame = {
  boardSize: number;
  firstTurn: number;
  currentGameNumber: number;
  seriesLength: number;
  player1Wins: number;
  player2Wins: number;
  winsRequired: number;
  playerModels: Record<string, string>;
  playerUsernames: Record<string, string>;
};

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
  pendingNextGame: PendingGame | null;
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
  pendingNextGame: null,
};

function applyPendingGame(s: GameState, pg: PendingGame): GameState {
  return {
    ...s,
    phase: "playing",
    board: Array.from({ length: pg.boardSize }, () => Array<number>(pg.boardSize).fill(0)),
    boardSize: pg.boardSize,
    currentTurn: pg.firstTurn,
    winner: null,
    player1Wins: pg.player1Wins,
    player2Wins: pg.player2Wins,
    seriesLength: pg.seriesLength,
    winsRequired: pg.winsRequired,
    currentGame: pg.currentGameNumber,
    playerModels: pg.playerModels,
    playerUsernames: pg.playerUsernames,
    pendingNextGame: null,
    errorMessage: null,
  };
}

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
        const pg: PendingGame = {
          boardSize: p.board_size as number,
          firstTurn: p.first_turn as number,
          currentGameNumber: p.current_game_number as number,
          seriesLength: p.series_length as number,
          player1Wins: p.player_1_wins as number,
          player2Wins: p.player_2_wins as number,
          winsRequired: p.wins_required as number,
          playerModels: ((p.player_models ?? {}) as Record<string, string>),
          playerUsernames: ((p.player_usernames ?? {}) as Record<string, string>),
        };
        setState((s) =>
          s.phase === "game_over" && s.seriesLength > 1
            ? { ...s, pendingNextGame: pg }
            : applyPendingGame({ ...s, pendingNextGame: null }, pg)
        );
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
  const [nextGameCountdown, setNextGameCountdown] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const close = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const join = useCallback(
    (username: string, boardSize: number, seriesLength: number, firstPlayer?: number) => {
      close();
      setState({ ...INITIAL, phase: "waiting", boardSize, seriesLength });
      let url = `${wsBase()}/ws/matchmake?board_size=${boardSize}&series_length=${seriesLength}&model_name=human&username=${encodeURIComponent(username)}`;
      if (firstPlayer !== undefined) url += `&first_player=${firstPlayer}`;
      attachHandlers(new WebSocket(url), wsRef, setState);
    },
    [close]
  );

  const joinSlot = useCallback(
    (username: string, slotId: number) => {
      close();
      setState({ ...INITIAL, phase: "waiting" });
      const url = `${wsBase()}/ws/join-slot?slot_id=${slotId}&model_name=human&username=${encodeURIComponent(username)}`;
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

  useEffect(() => {
    const pg = state.pendingNextGame;
    if (!pg) {
      setNextGameCountdown(null);
      return;
    }
    const seconds = Math.round(BETWEEN_GAME_DELAY_MS / 1000);
    setNextGameCountdown(seconds);
    const tick = setInterval(() => {
      setNextGameCountdown((n) => (n !== null && n > 1 ? n - 1 : n));
    }, 1000);
    const apply = setTimeout(() => {
      setState((s) => s.pendingNextGame ? applyPendingGame(s, s.pendingNextGame) : s);
    }, BETWEEN_GAME_DELAY_MS);
    return () => {
      clearInterval(tick);
      clearTimeout(apply);
    };
  }, [state.pendingNextGame]);

  useEffect(() => () => close(), [close]);

  return { state, nextGameCountdown, join, joinSlot, sendMove, reconnect, reset };
}
