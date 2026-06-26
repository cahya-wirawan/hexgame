import { useCallback, useEffect, useRef, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export type DqnBotPhase = "idle" | "loading" | "connecting" | "waiting" | "playing" | "done" | "error";
export type BotMode = "dqn" | "minimax" | "mcts";

// ── Constants ─────────────────────────────────────────────────────────────────

const MINIMAX_DEPTH = 2;   // plies of lookahead; depth 3 is ~5-10× slower
const MCTS_N_SIMS = 200;   // PUCT simulations per move
const MCTS_C_PUCT = 1.5;
const MCTS_TEMP_PRIOR = 1.0;  // softmax(Q / T) temperature for priors

// ── Board helpers ─────────────────────────────────────────────────────────────
//
// Server board: board[r][q], PLAYER_1 = -1 (red, left↔right), PLAYER_2 = 1 (blue, top↔bottom)
// Hex neighbour offsets (dr, dq):

const NEIGHBORS: [number, number][] = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, -1], [-1, 1]];

function hasWon(board: number[][], r: number, q: number, player: number, n: number): boolean {
  // BFS from (r,q); check if the stone's connected component spans both edges.
  // player -1 (red): left edge q=0 to right edge q=n-1
  // player  1 (blue): top edge r=0 to bottom edge r=n-1
  const visited = new Set<number>([r * n + q]);
  const stack: [number, number][] = [[r, q]];
  let reachA = player === -1 ? q === 0 : r === 0;
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
      if (player === -1) {
        if (nq === 0)     reachA = true;
        if (nq === n - 1) reachB = true;
      } else {
        if (nr === 0)     reachA = true;
        if (nr === n - 1) reachB = true;
      }
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
  // Avoid weak corner/edge openers (mirrors Python DQN heuristic)
  const cells: [number, number][] = [];
  for (let r = 1; r < n - 1; r++)
    for (let q = 1; q < n - 1; q++)
      cells.push([r, q]);
  if (cells.length === 0) return [Math.floor(n / 2), Math.floor(n / 2)];
  return cells[Math.floor(Math.random() * cells.length)];
}

function cloneBoard(board: number[][]): number[][] {
  return board.map(row => [...row]);
}

// ── DQN perspective helpers ───────────────────────────────────────────────────
//
// Coordinate system notes (mirrors client_safety.py + model_dqn.py):
//   hex_engine: RED=1 (left↔right), BLUE=-1 (top↔bottom)
//   mapping:    hex_val = -server_val
//   perspective: model always sees itself as RED.
//   For PLAYER_2 (BLUE), recode_blue_as_red() applies:
//       persp[pr][pc] = -hex[n-1-pc][n-1-pr] = server[n-1-pc][n-1-pr]
//   recode_coordinates(r, q) = (n-1-q, n-1-r)

function buildDqnInput(board: number[][], myPlayer: number, n: number): Float32Array {
  const data = new Float32Array(2 * n * n);
  const isBlue = myPlayer === 1;

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
      data[idx]         = myStone  ? 1.0 : 0.0;  // channel 0: my stones (as RED)
      data[n * n + idx] = oppStone ? 1.0 : 0.0;  // channel 1: opponent (as BLUE)
    }
  }
  return data;
}

// Perspective-space index for move (r, q) when current player is `player`.
function perspIdx(r: number, q: number, player: number, n: number): number {
  if (player === -1) return r * n + q;
  // recode_coordinates(r, q) = (n-1-q, n-1-r)
  return (n - 1 - q) * n + (n - 1 - r);
}

// ── ONNX helpers ──────────────────────────────────────────────────────────────

type OrtModule = typeof import("onnxruntime-web");
type Session = Awaited<ReturnType<OrtModule["InferenceSession"]["create"]>>;

let _ort: OrtModule | null = null;

async function getOrt(): Promise<OrtModule> {
  if (!_ort) {
    _ort = await import("onnxruntime-web");
    _ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.27.0/dist/";
    _ort.env.wasm.numThreads = 1;
  }
  return _ort;
}

async function getQValues(
  session: Session,
  board: number[][],
  player: number,
  n: number,
  cache?: Map<string, Float32Array>,
): Promise<Float32Array> {
  const key = cache ? board.flat().join(",") + "_" + player : "";
  if (cache?.has(key)) return cache.get(key)!;

  const ort = await getOrt();
  const inputData = buildDqnInput(board, player, n);
  const tensor = new ort.Tensor("float32", inputData, [1, 2, n, n]);
  const output = await session.run({ board: tensor });
  const vals = output["q_values"].data as Float32Array;

  if (cache) cache.set(key, vals);
  return vals;
}

// ── Greedy DQN move ───────────────────────────────────────────────────────────

function pickGreedyMove(
  qValues: Float32Array,
  board: number[][],
  player: number,
  n: number,
): [number, number] {
  let bestVal = -Infinity, bestR = 0, bestQ = 0;
  for (let r = 0; r < n; r++) {
    for (let q = 0; q < n; q++) {
      if (board[r][q] !== 0) continue;
      const val = qValues[perspIdx(r, q, player, n)];
      if (val > bestVal) { bestVal = val; bestR = r; bestQ = q; }
    }
  }
  return [bestR, bestQ];
}

// ── Minimax (negamax α-β) ─────────────────────────────────────────────────────

type MoveUndo = { player: number; winner: number };

interface SearchState {
  board: number[][];
  player: number;  // the player ABOUT TO MOVE
  winner: number;  // 0 = game ongoing
  n: number;
}

function applyMove(state: SearchState, r: number, q: number): MoveUndo {
  const prev = { player: state.player, winner: state.winner };
  state.board[r][q] = state.player;
  state.winner = hasWon(state.board, r, q, state.player, state.n) ? state.player : 0;
  state.player = -state.player;
  return prev;
}

function undoMove(state: SearchState, r: number, q: number, undo: MoveUndo): void {
  state.board[r][q] = 0;
  state.player = undo.player;
  state.winner = undo.winner;
}

async function alphabeta(
  state: SearchState,
  depth: number,
  alpha: number,
  beta: number,
  session: Session,
  cache: Map<string, Float32Array>,
): Promise<number> {
  // game.player has already flipped; if winner != 0, the PREVIOUS player won
  // ⇒ the CURRENT player (about to move) has lost → return -1
  if (state.winner !== 0) return -1.0;

  const cells = getEmpty(state.board, state.n);
  if (cells.length === 0) return 0.0;

  const qVals = await getQValues(session, state.board, state.player, state.n, cache);

  if (depth === 0) {
    // Leaf: best legal Q from current player's POV
    let best = -Infinity;
    for (const [r, q] of cells) {
      const v = qVals[perspIdx(r, q, state.player, state.n)];
      if (v > best) best = v;
    }
    return best;
  }

  // Best-first ordering for tight α-β cuts
  cells.sort(
    (a, b) =>
      qVals[perspIdx(b[0], b[1], state.player, state.n)] -
      qVals[perspIdx(a[0], a[1], state.player, state.n)],
  );

  let best = -Infinity;
  for (const [r, q] of cells) {
    const undo = applyMove(state, r, q);
    const val = -(await alphabeta(state, depth - 1, -beta, -alpha, session, cache));
    undoMove(state, r, q, undo);
    if (val > best) best = val;
    if (best > alpha) alpha = best;
    if (alpha >= beta) break;
  }
  return best;
}

async function minimaxSearch(
  board: number[][],
  player: number,
  n: number,
  session: Session,
): Promise<[number, number]> {
  if (isEmptyBoard(board, n)) return randomInterior(n);

  const state: SearchState = { board: cloneBoard(board), player, winner: 0, n };
  const cache = new Map<string, Float32Array>();
  const qVals = await getQValues(session, state.board, player, n, cache);
  const cells = getEmpty(state.board, n);

  cells.sort(
    (a, b) =>
      qVals[perspIdx(b[0], b[1], player, n)] - qVals[perspIdx(a[0], a[1], player, n)],
  );

  let bestMove = cells[0];
  let bestScore = -Infinity;
  let alpha = -Infinity;

  for (const [r, q] of cells) {
    const undo = applyMove(state, r, q);
    const val = -(await alphabeta(state, MINIMAX_DEPTH - 1, -Infinity, -alpha, session, cache));
    undoMove(state, r, q, undo);
    if (val > bestScore) { bestScore = val; bestMove = [r, q]; }
    if (val > alpha) alpha = val;
  }
  return bestMove;
}

// ── MCTS (PUCT with DQN prior + value) ───────────────────────────────────────

interface MctsNode {
  board: number[][];
  n: number;
  player: number;  // player ABOUT TO MOVE
  winner: number;
  parent: MctsNode | null;
  move: [number, number] | null;
  children: Map<string, MctsNode>;  // key = "r,q"
  N: number;
  W: number;
  Q: number;
  P: number;       // prior probability
  expanded: boolean;
}

function makeNode(
  board: number[][],
  n: number,
  player: number,
  winner: number,
  parent: MctsNode | null,
  move: [number, number] | null,
  prior: number,
): MctsNode {
  return { board, n, player, winner, parent, move, children: new Map(), N: 0, W: 0, Q: 0, P: prior, expanded: false };
}

function puctScore(child: MctsNode, cPuct: number): number {
  // child.Q is from child's player POV → negate for parent's perspective
  const sqrtN = child.parent ? Math.sqrt(child.parent.N) : 1.0;
  return -child.Q + cPuct * child.P * sqrtN / (1 + child.N);
}

function selectPath(root: MctsNode, cPuct: number): MctsNode[] {
  const path: MctsNode[] = [];
  let node = root;
  while (node.expanded && node.winner === 0) {
    path.push(node);
    let best = -Infinity, chosen = node.children.values().next().value as MctsNode;
    for (const child of node.children.values()) {
      const s = puctScore(child, cPuct);
      if (s > best) { best = s; chosen = child; }
    }
    node = chosen;
  }
  path.push(node);
  return path;
}

async function expandNode(node: MctsNode, session: Session): Promise<number> {
  // Returns V(s) = max legal Q from current player's POV
  const { n, board, player } = node;
  const qVals = await getQValues(session, board, player, n);

  // Leaf value: max legal Q, clipped to [-1, 1]
  const cells = getEmpty(board, n);
  let maxQ = -Infinity;
  for (const [r, q] of cells) {
    const v = qVals[perspIdx(r, q, player, n)];
    if (v > maxQ) maxQ = v;
  }
  const v = Math.max(-1.0, Math.min(1.0, maxQ));

  // Priors: softmax(Q / T) over legal moves only
  const legalQ: number[] = cells.map(([r, q]) => qVals[perspIdx(r, q, player, n)] / MCTS_TEMP_PRIOR);
  const maxLQ = Math.max(...legalQ);
  const exps = legalQ.map(x => Math.exp(x - maxLQ));
  const sumExp = exps.reduce((a, b) => a + b, 0);
  const priors = exps.map(e => e / sumExp);

  // Create child nodes (board copies with the move applied)
  cells.forEach(([r, q], i) => {
    const childBoard = cloneBoard(board);
    childBoard[r][q] = player;
    const childWinner = hasWon(childBoard, r, q, player, n) ? player : 0;
    const childPlayer = -player;
    node.children.set(`${r},${q}`, makeNode(childBoard, n, childPlayer, childWinner, node, [r, q], priors[i]));
  });
  node.expanded = true;
  return v;
}

function backup(path: MctsNode[], v: number): void {
  for (let i = path.length - 1; i >= 0; i--) {
    const node = path[i];
    node.N += 1;
    node.W += v;
    node.Q = node.W / node.N;
    v = -v;
  }
}

async function mctsSearch(
  board: number[][],
  player: number,
  n: number,
  session: Session,
): Promise<[number, number]> {
  if (isEmptyBoard(board, n)) return randomInterior(n);

  const root = makeNode(cloneBoard(board), n, player, 0, null, null, 0.0);
  await expandNode(root, session);

  for (let sim = 0; sim < MCTS_N_SIMS; sim++) {
    const path = selectPath(root, MCTS_C_PUCT);
    const leaf = path[path.length - 1];

    let v: number;
    if (leaf.winner !== 0) {
      v = -1.0;  // current player at this node just lost
    } else {
      v = await expandNode(leaf, session);
    }
    backup(path, v);
  }

  // Pick most-visited child
  let bestVisits = -1, bestMove: [number, number] = [0, 0];
  for (const [key, child] of root.children) {
    if (child.N > bestVisits) {
      bestVisits = child.N;
      const [r, q] = key.split(",").map(Number);
      bestMove = [r, q];
    }
  }
  return bestMove;
}

// ── Top-level move dispatcher ─────────────────────────────────────────────────

async function computeMove(
  session: Session,
  board: number[][],
  player: number,
  n: number,
  mode: BotMode,
): Promise<{ q: number; r: number }> {
  let r: number, q: number;

  if (mode === "minimax") {
    [r, q] = await minimaxSearch(board, player, n, session);
  } else if (mode === "mcts") {
    [r, q] = await mctsSearch(board, player, n, session);
  } else {
    // Greedy DQN
    if (isEmptyBoard(board, n)) {
      [r, q] = randomInterior(n);
    } else {
      const qVals = await getQValues(session, board, player, n);
      [r, q] = pickGreedyMove(qVals, board, player, n);
    }
  }

  return { q, r };
}

// ── WebSocket helpers ─────────────────────────────────────────────────────────

function wsBase() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
}

// ── React hook ────────────────────────────────────────────────────────────────

export function useDqnBot() {
  const [phase, setPhase] = useState<DqnBotPhase>("idle");
  const [slotId, setSlotId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const myPlayerRef = useRef<number | null>(null);
  const boardRef = useRef<number[][] | null>(null);
  const boardSizeRef = useRef<number>(7);
  const modeRef = useRef<BotMode>("dqn");

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
    async (boardSize: number, mode: BotMode = "dqn"): Promise<number> => {
      stop();
      setPhase("loading");
      modeRef.current = mode;

      await getOrt();  // configure wasmPaths once

      if (!sessionRef.current || boardSizeRef.current !== boardSize) {
        const ort = await getOrt();
        sessionRef.current = await ort.InferenceSession.create(
          `/models/dqn_${boardSize}x${boardSize}.onnx`,
          { executionProviders: ["wasm"] },
        );
        boardSizeRef.current = boardSize;
      }
      const session = sessionRef.current;

      setPhase("connecting");

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
                const move = await computeMove(session, boardRef.current, myPlayerRef.current!, n, modeRef.current);
                ws.send(JSON.stringify({ type: "move", payload: move }));
              }
              break;

            case "move": {
              if (boardRef.current)
                boardRef.current[p.r as number][p.q as number] = p.player as number;
              if ((p.next_turn as number | null) === myPlayerRef.current && boardRef.current) {
                const move = await computeMove(session, boardRef.current, myPlayerRef.current!, n, modeRef.current);
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
