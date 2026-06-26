import { useCallback, useEffect, useRef, useState } from "react";

export type DqnBotPhase = "idle" | "loading" | "connecting" | "waiting" | "playing" | "done" | "error";

// Coordinate system notes:
// Server board:    board[r][q], PLAYER_1=-1 (red, left↔right), PLAYER_2=1 (blue, top↔bottom)
// hex_engine:      board[row][col], RED=1 (left↔right), BLUE=-1 (top↔bottom)
// Mapping:         hex_val = -server_val  (sign flip)
//
// DQN always infers from RED's perspective. When bot is PLAYER_2 (BLUE),
// recode_blue_as_red() is applied:  persp[row][col] = -hex[n-1-col][n-1-row]
//                                                    = server[n-1-col][n-1-row]
// recode_coordinates(r, q) = (n-1-q, n-1-r)

function wsBase() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
}

function buildDqnInput(board: number[][], myPlayer: number, n: number): Float32Array {
  const data = new Float32Array(2 * n * n);
  const isBlue = myPlayer === 1;

  for (let pr = 0; pr < n; pr++) {
    for (let pc = 0; pc < n; pc++) {
      let myStone: boolean;
      let oppStone: boolean;

      if (!isBlue) {
        // PLAYER_1 (RED in hex_engine): no perspective transform
        // server -1 = PLAYER_1 = RED = my stone
        myStone = board[pr][pc] === -1;
        oppStone = board[pr][pc] === 1;
      } else {
        // PLAYER_2 (BLUE in hex_engine): recode_blue_as_red perspective
        // persp[pr][pc] samples from original position (n-1-pc, n-1-pr)
        // After recoding: server 1 (my PLAYER_2 stone) appears as RED in perspective
        const origR = n - 1 - pc;
        const origQ = n - 1 - pr;
        myStone = board[origR][origQ] === 1;
        oppStone = board[origR][origQ] === -1;
      }

      const idx = pr * n + pc;
      data[idx] = myStone ? 1.0 : 0.0;            // channel 0: my stones viewed as RED
      data[n * n + idx] = oppStone ? 1.0 : 0.0;   // channel 1: opponent's stones viewed as BLUE
    }
  }

  return data;
}

function pickBestMove(
  qValues: Float32Array,
  board: number[][],
  myPlayer: number,
  n: number,
): { q: number; r: number } {
  const isBlue = myPlayer === 1;
  let bestVal = -Infinity;
  let bestR = 0;
  let bestQ = 0;
  let found = false;

  for (let r = 0; r < n; r++) {
    for (let q = 0; q < n; q++) {
      if (board[r][q] !== 0) continue;

      // Map server (r, q) to perspective space index
      let perspIdx: number;
      if (!isBlue) {
        perspIdx = r * n + q;
      } else {
        // recode_coordinates(r, q) = (n-1-q, n-1-r)
        const pr = n - 1 - q;
        const pc = n - 1 - r;
        perspIdx = pr * n + pc;
      }

      if (qValues[perspIdx] > bestVal) {
        bestVal = qValues[perspIdx];
        bestR = r;
        bestQ = q;
        found = true;
      }
    }
  }

  if (!found) {
    for (let r = 0; r < n; r++) {
      for (let q = 0; q < n; q++) {
        if (board[r][q] === 0) return { q, r };
      }
    }
  }

  return { q: bestQ, r: bestR };
}

type InferenceSession = Awaited<ReturnType<typeof import("onnxruntime-web")["InferenceSession"]["create"]>>;

async function runInference(
  session: InferenceSession,
  board: number[][],
  myPlayer: number,
  n: number,
): Promise<{ q: number; r: number }> {
  const { Tensor } = await import("onnxruntime-web");
  const inputData = buildDqnInput(board, myPlayer, n);
  const tensor = new Tensor("float32", inputData, [1, 2, n, n]);
  const output = await session.run({ board: tensor });
  const qValues = output["q_values"].data as Float32Array;
  return pickBestMove(qValues, board, myPlayer, n);
}

export function useDqnBot() {
  const [phase, setPhase] = useState<DqnBotPhase>("idle");
  const [slotId, setSlotId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const sessionRef = useRef<InferenceSession | null>(null);
  const myPlayerRef = useRef<number | null>(null);
  const boardRef = useRef<number[][] | null>(null);
  const boardSizeRef = useRef<number>(7);

  const stop = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    myPlayerRef.current = null;
    boardRef.current = null;
    setPhase("idle");
    setSlotId(null);
    setErrorMessage(null);
  }, []);

  const start = useCallback(
    async (boardSize: number): Promise<number> => {
      stop();
      setPhase("loading");

      // Lazy-load onnxruntime-web and configure WASM path
      const ort = await import("onnxruntime-web");
      ort.env.wasm.wasmPaths = `https://cdn.jsdelivr.net/npm/onnxruntime-web@1.27.0/dist/`;
      ort.env.wasm.numThreads = 1;

      // Load (and cache) the ONNX session for this board size
      if (!sessionRef.current || boardSizeRef.current !== boardSize) {
        sessionRef.current = await ort.InferenceSession.create(
          `/models/dqn_${boardSize}x${boardSize}.onnx`,
          { executionProviders: ["wasm"] },
        );
        boardSizeRef.current = boardSize;
      }
      const session = sessionRef.current;

      setPhase("connecting");

      // Bot joins matchmaking first; the human will join its slot via /ws/join-slot
      return new Promise<number>((resolve, reject) => {
        const url = `${wsBase()}/ws/matchmake?board_size=${boardSize}&series_length=1&model_name=dqn&username=DQN+Bot`;
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onmessage = async (ev: MessageEvent) => {
          const { type, payload: p } = JSON.parse(ev.data as string) as {
            type: string;
            payload: Record<string, unknown>;
          };

          const n = boardSizeRef.current;

          switch (type) {
            case "joined":
              myPlayerRef.current = p.player as number;
              setSlotId(p.slot_id as number);
              setPhase("waiting");
              resolve(p.slot_id as number);
              break;

            case "game_start":
              boardRef.current = Array.from({ length: n }, () => Array<number>(n).fill(0));
              setPhase("playing");
              if ((p.first_turn as number) === myPlayerRef.current && boardRef.current) {
                const move = await runInference(session, boardRef.current, myPlayerRef.current!, n);
                ws.send(JSON.stringify({ type: "move", payload: move }));
              }
              break;

            case "move": {
              if (boardRef.current) {
                boardRef.current[p.r as number][p.q as number] = p.player as number;
              }
              if (
                (p.next_turn as number | null) === myPlayerRef.current &&
                boardRef.current
              ) {
                const move = await runInference(session, boardRef.current, myPlayerRef.current!, n);
                ws.send(JSON.stringify({ type: "move", payload: move }));
              }
              break;
            }

            case "series_update":
              boardRef.current = Array.from({ length: n }, () => Array<number>(n).fill(0));
              break;

            case "series_over":
            case "game_over":
              setPhase("done");
              break;

            case "error":
              setPhase("error");
              setErrorMessage(String(p.message));
              reject(new Error(String(p.message)));
              break;
          }
        };

        ws.onerror = () => {
          setPhase("error");
          setErrorMessage("DQN bot WebSocket error");
          reject(new Error("DQN bot WebSocket error"));
        };

        ws.onclose = () => {
          setPhase((prev) => (prev === "done" || prev === "error" ? prev : "idle"));
        };
      });
    },
    [stop],
  );

  useEffect(() => () => stop(), [stop]);

  return { phase, slotId, errorMessage, start, stop };
}
