import { useCallback, useEffect, useRef, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export type AZBotPhase = "idle" | "loading" | "connecting" | "waiting" | "playing" | "done" | "error";

// ── Constants ─────────────────────────────────────────────────────────────────

const AZ_MCTS_SIMS = 100;   // ONNX inference per move; Python uses 200-800
const AZ_C_PUCT    = 1.5;

// ── Board helpers ─────────────────────────────────────────────────────────────
//
// Server board: board[r][q], PLAYER_1=-1 (red, left↔right), PLAYER_2=1 (blue, top↔bottom)

const NEIGHBORS: [number, number][] = [[1,0],[-1,0],[0,1],[0,-1],[1,-1],[-1,1]];

function hasWon(board: number[][], r: number, q: number, player: number, n: number): boolean {
  const visited = new Set<number>([r * n + q]);
  const stack: [number, number][] = [[r, q]];
  let reachA = player === -1 ? q === 0     : r === 0;
  let reachB = player === -1 ? q === n - 1 : r === n - 1;
  while (stack.length > 0 && !(reachA && reachB)) {
    const [cr, cq] = stack.pop()!;
    for (const [dr, dq] of NEIGHBORS) {
      const nr = cr + dr, nq = cq + dq;
      if (nr < 0 || nr >= n || nq < 0 || nq >= n) continue;
      if (board[nr][nq] !== player) continue;
      const key = nr * n + nq;
      if (visited.has(key)) continue;
      visited.add(key);
      if (player === -1) { if (nq === 0) reachA = true; if (nq === n-1) reachB = true; }
      else               { if (nr === 0) reachA = true; if (nr === n-1) reachB = true; }
      stack.push([nr, nq]);
    }
  }
  return reachA && reachB;
}

function getEmpty(board: number[][], n: number): [number, number][] {
  const cells: [number, number][] = [];
  for (let r = 0; r < n; r++)
    for (let q = 0; q < n; q++)
      if (board[r][q] === 0) cells.push([r, q]);
  return cells;
}

function isEmptyBoard(board: number[][], n: number): boolean {
  return board.every(row => row.every(c => c === 0));
}

function randomInterior(n: number): [number, number] {
  const cells: [number, number][] = [];
  for (let r = 1; r < n - 1; r++)
    for (let q = 1; q < n - 1; q++)
      cells.push([r, q]);
  if (!cells.length) return [Math.floor(n / 2), Math.floor(n / 2)];
  return cells[Math.floor(Math.random() * cells.length)];
}

function cloneBoard(board: number[][]): number[][] {
  return board.map(row => [...row]);
}

// ── Perspective helpers ───────────────────────────────────────────────────────
//
// The network always sees the board from the current player's POV as RED (left↔right).
// For PLAYER_2 (blue) this applies recode_blue_as_red:
//   perspBoard[pr][pc] = serverBoard[n-1-pc][n-1-pr]
// recode_coordinates(r, q) = (n-1-q, n-1-r)
//
// perspIdx: maps a server-coord move (r,q) to its flat perspective index.

function perspIdx(r: number, q: number, player: number, n: number): number {
  if (player === -1) return r * n + q;
  return (n - 1 - q) * n + (n - 1 - r);
}

function buildAZInput(board: number[][], player: number, n: number): Float32Array {
  const data = new Float32Array(2 * n * n);
  const isBlue = player === 1;
  for (let pr = 0; pr < n; pr++) {
    for (let pc = 0; pc < n; pc++) {
      let myStone: boolean, oppStone: boolean;
      if (!isBlue) {
        myStone  = board[pr][pc] === -1;
        oppStone = board[pr][pc] ===  1;
      } else {
        const origR = n - 1 - pc, origQ = n - 1 - pr;
        myStone  = board[origR][origQ] ===  1;
        oppStone = board[origR][origQ] === -1;
      }
      const idx = pr * n + pc;
      data[idx]         = myStone  ? 1.0 : 0.0;
      data[n * n + idx] = oppStone ? 1.0 : 0.0;
    }
  }
  return data;
}

// Validity mask for softmax: 0 for empty cells, -Infinity for occupied ones.
// Derived from the input channels (ch0+ch1 > 0 ⟹ occupied in perspective space).
function buildValidityMask(board: number[][], player: number, n: number): Float32Array {
  const input = buildAZInput(board, player, n);
  const mask  = new Float32Array(n * n);
  for (let i = 0; i < n * n; i++)
    if (input[i] > 0 || input[n * n + i] > 0)
      mask[i] = -Infinity;
  return mask;
}

// ── ONNX helpers ──────────────────────────────────────────────────────────────

type OrtModule = typeof import("onnxruntime-web");
type Session   = Awaited<ReturnType<OrtModule["InferenceSession"]["create"]>>;

let _ort: OrtModule | null = null;

async function getOrt(): Promise<OrtModule> {
  if (!_ort) {
    _ort = await import("onnxruntime-web");
    _ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.27.0/dist/";
    _ort.env.wasm.numThreads = 1;
  }
  return _ort;
}

async function runNet(
  session: Session,
  board: number[][],
  player: number,
  n: number,
): Promise<{ logits: Float32Array; value: number }> {
  const ort      = await getOrt();
  const inputData = buildAZInput(board, player, n);
  const tensor   = new ort.Tensor("float32", inputData, [1, 2, n, n]);
  const output   = await session.run({ board: tensor });
  return {
    logits: output["policy_logits"].data as Float32Array,
    value:  (output["value"].data as Float32Array)[0],
  };
}

// ── MCTS ──────────────────────────────────────────────────────────────────────

interface AZNode {
  board: number[][];
  n: number;
  player: number;
  winner: number;
  parent: AZNode | null;
  move: [number, number] | null;
  children: Map<string, AZNode>;
  N: number;
  W: number;
  Q: number;
  P: number;
  expanded: boolean;
}

function makeNode(
  board: number[][],
  n: number,
  player: number,
  winner: number,
  parent: AZNode | null,
  move: [number, number] | null,
  prior: number,
): AZNode {
  return { board, n, player, winner, parent, move, children: new Map(), N: 0, W: 0, Q: 0, P: prior, expanded: false };
}

function selectPath(root: AZNode): AZNode[] {
  const path: AZNode[] = [];
  let node = root;
  while (node.expanded && node.winner === 0) {
    path.push(node);
    const sqrtN = Math.sqrt(node.N);
    let best = -Infinity, chosen = node.children.values().next().value as AZNode;
    for (const child of node.children.values()) {
      const score = -child.Q + AZ_C_PUCT * child.P * sqrtN / (1 + child.N);
      if (score > best) { best = score; chosen = child; }
    }
    node = chosen;
  }
  path.push(node);
  return path;
}

async function expandNode(node: AZNode, session: Session): Promise<number> {
  const { n, board, player } = node;
  const { logits, value } = await runNet(session, board, player, n);

  // Masked softmax → priors for each empty cell
  const mask   = buildValidityMask(board, player, n);
  const cells  = getEmpty(board, n);
  let maxL = -Infinity;
  for (const [r, q] of cells) {
    const pi = perspIdx(r, q, player, n);
    const v  = logits[pi] + mask[pi];  // mask[pi] == 0 since cell is empty
    if (v > maxL) maxL = v;
  }
  const exps   = cells.map(([r, q]) => Math.exp(logits[perspIdx(r, q, player, n)] - maxL));
  const sumExp = exps.reduce((a, b) => a + b, 0);

  cells.forEach(([r, q], i) => {
    const prior      = sumExp > 0 ? exps[i] / sumExp : 1 / cells.length;
    const childBoard = cloneBoard(board);
    childBoard[r][q] = player;
    const childWinner = hasWon(childBoard, r, q, player, n) ? player : 0;
    node.children.set(`${r},${q}`, makeNode(childBoard, n, -player, childWinner, node, [r, q], prior));
  });
  node.expanded = true;
  return value;  // [-1, 1] from current player's perspective
}

function backup(path: AZNode[], v: number): void {
  for (let i = path.length - 1; i >= 0; i--) {
    const node = path[i];
    node.N += 1;
    node.W += v;
    node.Q  = node.W / node.N;
    v = -v;
  }
}

async function azMctsSearch(
  board: number[][],
  player: number,
  n: number,
  session: Session,
  nSims: number,
): Promise<[number, number]> {
  if (isEmptyBoard(board, n)) return randomInterior(n);

  const root = makeNode(cloneBoard(board), n, player, 0, null, null, 0.0);
  await expandNode(root, session);

  for (let sim = 0; sim < nSims; sim++) {
    const path = selectPath(root);
    const leaf = path[path.length - 1];
    let v: number;
    if (leaf.winner !== 0) {
      v = -1.0;  // leaf player just lost (previous player placed winning stone)
    } else {
      v = await expandNode(leaf, session);
    }
    backup(path, v);
  }

  let bestN = -1;
  let bestMove: [number, number] = [0, 0];
  for (const [key, child] of root.children) {
    if (child.N > bestN) {
      bestN = child.N;
      const [r, q] = key.split(",").map(Number);
      bestMove = [r, q];
    }
  }
  return bestMove;
}

// ── WebSocket helper ──────────────────────────────────────────────────────────

function wsBase() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
}

// ── React hook ────────────────────────────────────────────────────────────────

export function useAlphaZeroBot() {
  const [phase, setPhase]          = useState<AZBotPhase>("idle");
  const [slotId, setSlotId]        = useState<number | null>(null);
  const [errorMessage, setError]   = useState<string | null>(null);

  const wsRef         = useRef<WebSocket | null>(null);
  const sessionRef    = useRef<Session | null>(null);
  const myPlayerRef   = useRef<number | null>(null);
  const boardRef      = useRef<number[][] | null>(null);
  const boardSizeRef  = useRef<number>(7);
  const nSimsRef      = useRef<number>(AZ_MCTS_SIMS);

  const stop = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    myPlayerRef.current = null;
    boardRef.current    = null;
    setPhase("idle");
    setSlotId(null);
    setError(null);
  }, []);

  const start = useCallback(
    async (
      boardSize: number,
      seriesLength: number = 1,
      firstPlayer: number  = -1,
      nSims: number        = AZ_MCTS_SIMS,
    ): Promise<number> => {
      stop();
      setPhase("loading");
      nSimsRef.current = nSims;

      await getOrt();  // configure wasmPaths once

      if (!sessionRef.current || boardSizeRef.current !== boardSize) {
        const ort = await getOrt();
        sessionRef.current = await ort.InferenceSession.create(
          `/models/alphazero_${boardSize}x${boardSize}.onnx`,
          { executionProviders: ["wasm"] },
        );
        boardSizeRef.current = boardSize;
      }
      const session = sessionRef.current;

      setPhase("connecting");

      return new Promise<number>((resolve, reject) => {
        const url = `${wsBase()}/ws/matchmake?board_size=${boardSize}&series_length=${seriesLength}&model_name=alphazero&username=AlphaZero+Bot&first_player=${firstPlayer}`;
        const ws  = new WebSocket(url);
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
                const [r, q] = await azMctsSearch(boardRef.current, myPlayerRef.current!, n, session, nSimsRef.current);
                ws.send(JSON.stringify({ type: "move", payload: { q, r } }));
              }
              break;

            case "move": {
              if (boardRef.current)
                boardRef.current[p.r as number][p.q as number] = p.player as number;
              if ((p.next_turn as number | null) === myPlayerRef.current && boardRef.current) {
                const [r, q] = await azMctsSearch(boardRef.current, myPlayerRef.current!, n, session, nSimsRef.current);
                ws.send(JSON.stringify({ type: "move", payload: { q, r } }));
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
              setError(String(p.message));
              reject(new Error(String(p.message)));
              break;
          }
        };

        ws.onerror = () => {
          setPhase("error");
          setError("AlphaZero bot WebSocket error");
          reject(new Error("AlphaZero bot WebSocket error"));
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
