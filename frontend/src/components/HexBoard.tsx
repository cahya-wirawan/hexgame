import { useMemo } from "react";

const S = 24;
const W = Math.sqrt(3) * S;
const PAD = 36;

function hexCenter(r: number, q: number) {
  return {
    cx: PAD + (q + r * 0.5) * W,
    cy: PAD + r * 1.5 * S,
  };
}

function hexPoints(cx: number, cy: number): string {
  return Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 180) * (30 + 60 * i);
    return `${cx + S * Math.cos(a)},${cy + S * Math.sin(a)}`;
  }).join(" ");
}

function hexVertex(r: number, q: number, i: number): [number, number] {
  const { cx, cy } = hexCenter(r, q);
  const a = (Math.PI / 180) * (30 + 60 * i);
  return [cx + S * Math.cos(a), cy + S * Math.sin(a)];
}

function borderPolyline(n: number, edge: "top" | "bottom" | "left" | "right"): string {
  const pts: [number, number][] = [];
  if (edge === "top") {
    pts.push(hexVertex(0, 0, 3));
    for (let q = 0; q < n; q++) { pts.push(hexVertex(0, q, 4)); pts.push(hexVertex(0, q, 5)); }
  } else if (edge === "bottom") {
    pts.push(hexVertex(n - 1, 0, 2));
    for (let q = 0; q < n; q++) { pts.push(hexVertex(n - 1, q, 1)); pts.push(hexVertex(n - 1, q, 0)); }
  } else if (edge === "left") {
    pts.push(hexVertex(0, 0, 4));
    for (let r = 0; r < n; r++) { pts.push(hexVertex(r, 0, 3)); pts.push(hexVertex(r, 0, 2)); }
  } else {
    pts.push(hexVertex(0, n - 1, 5));
    for (let r = 0; r < n; r++) { pts.push(hexVertex(r, n - 1, 0)); pts.push(hexVertex(r, n - 1, 1)); }
  }
  return pts.map(([x, y]) => `${x},${y}`).join(" ");
}

export function computeWinningPath(board: number[][], winner: number, n: number): Set<string> {
  const isStart = winner === -1 ? (_r: number, q: number) => q === 0 : (r: number) => r === 0;
  const isEnd   = winner === -1 ? (_r: number, q: number) => q === n - 1 : (r: number) => r === n - 1;
  const NBRS: [number, number][] = [[1,0],[-1,0],[0,1],[0,-1],[1,-1],[-1,1]];
  const key = (r: number, q: number) => `${r},${q}`;

  const parent = new Map<string, string | null>();
  const queue: [number, number][] = [];
  for (let r = 0; r < n; r++)
    for (let q = 0; q < n; q++)
      if (board[r][q] === winner && isStart(r, q)) {
        parent.set(key(r, q), null);
        queue.push([r, q]);
      }

  let endCell: [number, number] | null = null;
  let head = 0;
  outer: while (head < queue.length) {
    const [r, q] = queue[head++];
    if (isEnd(r, q)) { endCell = [r, q]; break outer; }
    for (const [dr, dq] of NBRS) {
      const nr = r + dr, nq = q + dq;
      if (nr < 0 || nr >= n || nq < 0 || nq >= n) continue;
      if (board[nr][nq] !== winner) continue;
      const nk = key(nr, nq);
      if (parent.has(nk)) continue;
      parent.set(nk, key(r, q));
      queue.push([nr, nq]);
    }
  }

  if (!endCell) return new Set();
  const path = new Set<string>();
  let cur: string | null = key(...endCell);
  while (cur !== null) { path.add(cur); cur = parent.get(cur) ?? null; }
  return path;
}

type Props = {
  board: number[][];
  boardSize: number;
  myPlayer: number | null;
  currentTurn: number | null;
  winner: number | null;
  onCellClick: (r: number, q: number) => void;
  disabled: boolean;
};

const RED   = "#df5146";
const BLUE  = "#2e7bd9";
const EMPTY = "#f4f8f4";
const WIN_RING = "#1a1a1a";

export function HexBoard({ board, boardSize: n, myPlayer, currentTurn, winner, onCellClick, disabled }: Props) {
  const winPath = useMemo(
    () => winner !== null ? computeWinningPath(board, winner, n) : null,
    [board, winner, n]
  );

  const isMyTurn = !disabled && currentTurn === myPlayer && winner === null;

  const svgW = PAD * 2 + (n - 1 + (n - 1) * 0.5) * W + W;
  const svgH = PAD * 2 + (n - 1) * 1.5 * S + 2 * S;

  return (
    <svg
      viewBox={`0 0 ${svgW} ${svgH}`}
      className="hex-board-svg"
      role="grid"
      aria-label="Hex board"
    >
      {/* Edge borders: red = left/right (player -1), blue = top/bottom (player 1) */}
      <polyline points={borderPolyline(n, "top")}    fill="none" stroke={BLUE} strokeWidth={S * 0.55} strokeLinejoin="round" opacity={0.7} />
      <polyline points={borderPolyline(n, "bottom")} fill="none" stroke={BLUE} strokeWidth={S * 0.55} strokeLinejoin="round" opacity={0.7} />
      <polyline points={borderPolyline(n, "left")}   fill="none" stroke={RED}  strokeWidth={S * 0.55} strokeLinejoin="round" opacity={0.7} />
      <polyline points={borderPolyline(n, "right")}  fill="none" stroke={RED}  strokeWidth={S * 0.55} strokeLinejoin="round" opacity={0.7} />

      {/* Cells */}
      {board.map((row, r) =>
        row.map((cell, q) => {
          const { cx, cy } = hexCenter(r, q);
          const pts = hexPoints(cx, cy);
          const inPath = winPath?.has(`${r},${q}`);
          const fill =
            cell === -1 ? RED :
            cell === 1  ? BLUE :
            EMPTY;
          const canClick = isMyTurn && cell === 0;

          return (
            <g key={`${r}-${q}`} role="gridcell" aria-label={`row ${r} col ${q}`}>
              <polygon
                points={pts}
                fill={fill}
                stroke={inPath ? WIN_RING : "#8aab8e"}
                strokeWidth={inPath ? 3 : 1}
                className={canClick ? "hex-cell-clickable" : ""}
                onClick={canClick ? () => onCellClick(r, q) : undefined}
              />
              {inPath && cell !== 0 && (
                <circle cx={cx} cy={cy} r={S * 0.3} fill={WIN_RING} opacity={0.25} pointerEvents="none" />
              )}
            </g>
          );
        })
      )}
    </svg>
  );
}
