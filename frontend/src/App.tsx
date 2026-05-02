import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader } from "./components/ui/card";

type SlotState = "empty" | "waiting" | "full";

type SlotSnapshot = {
  slot_id: number;
  state: SlotState;
  board_size: number | null;
  series_length: number | null;
  player_count: number;
  players: number[];
  current_turn: number | null;
  winner: number | null;
  move_count: number;
  board: (number | null)[][] | null;
  wins_required: number | null;
  current_game_number: number | null;
  player_1_wins: number;
  player_2_wins: number;
  series_winner: number | null;
};

const stateTone: Record<SlotState, "empty" | "waiting" | "full"> = {
  empty: "empty",
  waiting: "waiting",
  full: "full"
};

function BoardPreview({ board }: { board: SlotSnapshot["board"] }) {
  if (!board) {
    return <span className="text-sm text-slate-500">No board yet</span>;
  }

  return (
    <div className="grid max-w-52 gap-1" style={{ gridTemplateColumns: `repeat(${board.length}, minmax(0, 1fr))` }}>
      {board.flatMap((row, r) =>
        row.map((cell, q) => (
          <span
            key={`${q}-${r}`}
            className={
              cell === -1
                ? "aspect-square rounded-sm bg-red-600"
                : cell === 1
                  ? "aspect-square rounded-sm bg-blue-600"
                  : "aspect-square rounded-sm bg-slate-200"
            }
            title={`${q}, ${r}`}
          />
        ))
      )}
    </div>
  );
}

export default function App() {
  const [slots, setSlots] = useState<SlotSnapshot[]>([]);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch("/slots", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`);
      }
      const data = (await response.json()) as SlotSnapshot[];
      setSlots(data);
      setUpdatedAt(new Date());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load slots");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const totals = useMemo(() => {
    return slots.reduce(
      (acc, slot) => {
        acc[slot.state] += 1;
        return acc;
      },
      { empty: 0, waiting: 0, full: 0 } as Record<SlotState, number>
    );
  }, [slots]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6">
      <header className="flex flex-col gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">Hex Game Overview</h1>
          <p className="mt-1 text-sm text-slate-600">
            {updatedAt ? `Last updated ${updatedAt.toLocaleTimeString()}` : "Waiting for slot state"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="empty">Empty {totals.empty}</Badge>
          <Badge tone="waiting">Waiting {totals.waiting}</Badge>
          <Badge tone="full">Full {totals.full}</Badge>
          <Button onClick={() => void refresh()} disabled={isLoading} aria-label="Refresh slots">
            <RefreshCw className={isLoading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            Refresh
          </Button>
        </div>
      </header>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div> : null}

      <section className="grid gap-3 lg:grid-cols-2">
        {slots.map((slot) => (
          <Card key={slot.slot_id}>
            <CardHeader>
              <div>
                <h2 className="text-base font-semibold">Slot {slot.slot_id}</h2>
                <p className="text-sm text-slate-500">Board {slot.board_size ?? "unassigned"}</p>
              </div>
              <Badge tone={stateTone[slot.state]}>{slot.state}</Badge>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-[1fr_auto]">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-slate-500">Players</dt>
                  <dd className="font-medium">{slot.players.length ? slot.players.join(", ") : "None"}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Occupancy</dt>
                  <dd className="font-medium">{slot.player_count}/2</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Turn</dt>
                  <dd className="font-medium">{slot.current_turn ?? "None"}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Moves</dt>
                  <dd className="font-medium">{slot.move_count}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Series</dt>
                  <dd className="font-medium">
                    Best of {slot.series_length ?? 1}, game {slot.current_game_number ?? 1}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Score</dt>
                  <dd className="font-medium">
                    {slot.player_1_wins}-{slot.player_2_wins}
                    {slot.wins_required ? ` to ${slot.wins_required}` : ""}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Winner</dt>
                  <dd className="font-medium">
                    {slot.series_winner ? (
                      <Badge tone="winner">{slot.series_winner}</Badge>
                    ) : slot.winner ? (
                      <Badge tone="winner">{slot.winner}</Badge>
                    ) : (
                      "None"
                    )}
                  </dd>
                </div>
              </dl>
              <BoardPreview board={slot.board} />
            </CardContent>
          </Card>
        ))}
      </section>
    </main>
  );
}
