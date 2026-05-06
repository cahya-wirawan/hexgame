import { Activity, BookOpen, Code2, Database, GitBranch, RefreshCw, Swords, Terminal } from "lucide-react";
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
  connected_player_count: number;
  players: number[];
  player_models: Record<string, string>;
  player_usernames: Record<string, string>;
  connected_players: number[];
  disconnected_players: number[];
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

const playerGoals = [
  { player: -1, label: "player_1", color: "Red", goal: "Left to right", swatch: "bg-red-600" },
  { player: 1, label: "player_2", color: "Blue", goal: "Top to bottom", swatch: "bg-blue-600" }
];

const featureRows = [
  {
    icon: Swords,
    title: "Authoritative Hex",
    text: "The server owns identity, turns, move validation, win detection, and best-of series scoring."
  },
  {
    icon: Activity,
    title: "Live Match Operations",
    text: "Monitor slots, model names, owners, score, current turn, board preview, reconnect state, and waiting rooms."
  },
  {
    icon: GitBranch,
    title: "ML Client Ready",
    text: "Run random, first-move, DQN, PPO, GUI, or human clients against the same WebSocket protocol."
  },
  {
    icon: Database,
    title: "Persistence Path",
    text: "Use memory for local work, Redis for active state, and PostgreSQL history for completed series."
  }
];

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

function HeroBoard() {
  const stones = new Map([
    ["0-0", "red"],
    ["1-1", "blue"],
    ["2-1", "red"],
    ["3-2", "blue"],
    ["1-3", "red"],
    ["4-3", "blue"],
    ["3-4", "red"]
  ]);

  return (
    <div className="hero-board" aria-hidden="true">
      {Array.from({ length: 5 }).map((_, row) =>
        Array.from({ length: 5 }).map((_, col) => {
          const stone = stones.get(`${col}-${row}`);
          return (
            <span
              key={`${row}-${col}`}
              className={`hero-hex ${stone === "red" ? "hero-hex-red" : stone === "blue" ? "hero-hex-blue" : ""}`}
              style={{ left: `${col * 58 + row * 29}px`, top: `${row * 50}px` }}
            />
          );
        })
      )}
      <span className="hero-route hero-route-red" />
      <span className="hero-route hero-route-blue" />
    </div>
  );
}

function LandingPage({ totals }: { totals: Record<SlotState, number> }) {
  return (
    <>
      <section className="hero-section">
        <nav className="landing-nav">
          <a className="brand-mark" href="#top" aria-label="Hex Game Server home">
            <span className="brand-glyph">H</span>
            <span>Hex Game Server</span>
          </a>
          <div className="nav-links">
            <a href="#architecture">Architecture</a>
            <a href="/overview">Slots</a>
            <a href="/docs">Docs</a>
            <a href="#quickstart">Run</a>
          </div>
        </nav>

        <HeroBoard />

        <div className="hero-content">
          <p className="eyebrow">FastAPI · WebSockets · Redis · PostgreSQL · ML clients</p>
          <h1>Hex Game Server</h1>
          <p className="hero-copy">
            A precise, server-authoritative Hex arena for model-vs-model matches, human GUI play,
            reconnect-safe sessions, and live operational monitoring.
          </p>
          <div className="hero-actions">
            <a className="primary-link" href="/overview">
              <Activity className="h-4 w-4" />
              View live slots
            </a>
            <a className="secondary-link" href="#quickstart">
              <Terminal className="h-4 w-4" />
              Start locally
            </a>
            <a className="secondary-link" href="/docs">
              <BookOpen className="h-4 w-4" />
              Read docs
            </a>
          </div>
        </div>

        <div className="hero-status-strip" aria-label="Current slot summary">
          <span>
            <strong>{totals.waiting}</strong>
            waiting
          </span>
          <span>
            <strong>{totals.full}</strong>
            active
          </span>
          <span>
            <strong>{totals.empty}</strong>
            empty
          </span>
        </div>
      </section>

      <section id="architecture" className="landing-section">
        <div className="section-heading">
          <p className="eyebrow">Built for repeatable experiments</p>
          <h2>One protocol for games, models, humans, and operations.</h2>
        </div>
        <div className="feature-grid">
          {featureRows.map((feature) => {
            const Icon = feature.icon;
            return (
              <article className="feature-item" key={feature.title}>
                <span className="feature-icon">
                  <Icon className="h-5 w-5" />
                </span>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section id="quickstart" className="quickstart-section">
        <div>
          <p className="eyebrow">Local command</p>
          <h2>Launch the arena, then connect models or humans.</h2>
        </div>
        <pre>
          <code>{`python -m uvicorn app.main:app --port 8000
python -m examples.hex_client --model-name model_dqn --board-size 7
python -m examples.hex_client_gui --model-name human --slot-id 1`}</code>
        </pre>
      </section>
    </>
  );
}

function OverviewPage({
  slots,
  totals,
  updatedAt,
  error,
  isLoading,
  refresh
}: {
  slots: SlotSnapshot[];
  totals: Record<SlotState, number>;
  updatedAt: Date | null;
  error: string | null;
  isLoading: boolean;
  refresh: () => Promise<void>;
}) {
  return (
    <main id="top" className="min-h-screen">
      <section id="overview" className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-8 sm:px-6">
        <header className="flex flex-col gap-3 border-b border-emerald-200/80 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <a className="brand-mark overview-brand" href="/" aria-label="Go to Hex Game Server landing page">
              <span className="brand-glyph">H</span>
              <span>Hex Game Server</span>
            </a>
            <h1 className="text-2xl font-semibold text-slate-950">Live Slot Overview</h1>
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

        <div className="grid gap-3 lg:grid-cols-2">
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
                    <dd className="font-medium">
                      <PlayerList slot={slot} />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Occupancy</dt>
                    <dd className="font-medium">
                      {slot.connected_player_count ?? slot.player_count}/{slot.player_count || 2} connected
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Disconnected</dt>
                    <dd className="font-medium">
                      {slot.disconnected_players.length ? slot.disconnected_players.join(", ") : "None"}
                    </dd>
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
                  <div className="col-span-2">
                    <dt className="text-slate-500">Goal Directions</dt>
                    <dd className="mt-1 grid gap-1">
                      {playerGoals.map((goal) => (
                        <span key={goal.player} className="flex items-center gap-2 font-medium">
                          <span className={`h-2.5 w-2.5 rounded-sm ${goal.swatch}`} />
                          {goal.label} ({goal.player}, {goal.color}): {goal.goal}
                        </span>
                      ))}
                    </dd>
                  </div>
                </dl>
                <BoardPreview board={slot.board} />
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </main>
  );
}

function DocsPage() {
  return (
    <main id="top" className="docs-shell">
      <nav className="docs-nav">
        <a className="brand-mark overview-brand" href="/" aria-label="Go to Hex Game Server landing page">
          <span className="brand-glyph">H</span>
          <span>Hex Game Server</span>
        </a>
        <div className="nav-links">
          <a href="/overview">Slots</a>
          <a href="#run">Run</a>
          <a href="#model">Add a model</a>
          <a href="#protocol">Protocol</a>
        </div>
      </nav>

      <section className="docs-hero">
        <p className="eyebrow">Project documentation</p>
        <h1>Run games, connect clients, and add ML models.</h1>
        <p>
          Hex Game Server is a FastAPI WebSocket arena. The backend owns slot assignment,
          player identity, legal move validation, win detection, reconnect support, and
          best-of series scoring. ML clients only need to read state and return legal
          board coordinates.
        </p>
      </section>

      <section className="docs-grid" aria-label="Documentation sections">
        <article className="docs-card" id="run">
          <span className="docs-icon">
            <Terminal className="h-5 w-5" />
          </span>
          <h2>1. Use the hosted server</h2>
          <p>The provided clients default to <strong>wss://hexgame.codingdojo.ai</strong>, so you can connect models to the hosted arena without running the server locally. Install the client dependencies, add or choose a model, then start a client.</p>
          <pre>
            <code>{`git clone https://github.com/cahya-wirawan/hex-game-server.git
cd hex-game-server
python -m pip install -r requirements.txt
python -m examples.hex_client --model-name model_random --board-size 7
python -m examples.hex_client_gui --model-name human --board-size 7`}</code>
          </pre>
          <p>Open the hosted dashboard at <strong>https://hexgame.codingdojo.ai/overview</strong> to watch slots and match state.</p>
        </article>

        <article className="docs-card">
          <span className="docs-icon">
            <Swords className="h-5 w-5" />
          </span>
          <h2>2. Start matches</h2>
          <p>Use either matchmaking or a specific waiting slot. Board sizes and series lengths are validated by the server. The <strong>--server</strong> argument is optional for the hosted server because it is already the default.</p>
          <pre>
            <code>{`python -m examples.hex_client --board-size 7 --series-length 3 --model-name model_dqn
python -m examples.hex_client_gui --model-name human --slot-id 1
python -m examples.hex_client --model-name model_random --server wss://hexgame.codingdojo.ai`}</code>
          </pre>
          <p>Use <strong>--keep-slot</strong> when the first player should stay in the slot and wait for the next opponent after a series ends.</p>
        </article>

        <article className="docs-card" id="model">
          <span className="docs-icon">
            <Code2 className="h-5 w-5" />
          </span>
          <h2>3. Add a new ML model</h2>
          <p>The simplest workflow is to copy <strong>examples/model_random.py</strong> to a new file such as <strong>examples/model_my_agent.py</strong>, then replace the logic inside <strong>agent</strong>. Return one legal move from the provided <strong>action_set</strong>.</p>
          <pre>
            <code>{`cp examples/model_random.py examples/model_my_agent.py

# examples/model_my_agent.py
from random import choice

def agent(board, action_set):
    # board contains 0, -1, and 1
    # action_set contains legal (row, col) moves
    return choice(list(action_set))`}</code>
          </pre>
          <p>The client adapter expects numeric players: <strong>-1</strong> for red/player_1 and <strong>1</strong> for blue/player_2. The model returns <strong>(row, col)</strong>; the client converts it to the server <strong>{"{q, r}"}</strong> payload.</p>
        </article>

        <article className="docs-card">
          <span className="docs-icon">
            <Activity className="h-5 w-5" />
          </span>
          <h2>4. Wire the model into a client</h2>
          <p>Run the new module by passing its filename stem to either provided client. The clients dynamically import <strong>examples/model_my_agent.py</strong> when you use <strong>--model-name model_my_agent</strong>.</p>
          <pre>
            <code>{`python -m examples.hex_client --model-name model_my_agent --board-size 7
python -m examples.hex_client_gui --model-name model_my_agent --board-size 7
python -m examples.hex_client --model-name model_my_agent --slot-id 1`}</code>
          </pre>
          <p>For a quick smoke test, run your new model against <strong>model_random</strong> or the GUI human client and watch <strong>/overview</strong>. If the model returns a move that is not in <strong>action_set</strong>, the client rejects it before sending anything illegal to the server.</p>
        </article>

        <article className="docs-card" id="protocol">
          <span className="docs-icon">
            <GitBranch className="h-5 w-5" />
          </span>
          <h2>5. Protocol essentials</h2>
          <ul>
            <li>Join matchmaking with <strong>/ws/matchmake?board_size=7&amp;series_length=3&amp;model_name=name&amp;username=owner</strong>.</li>
            <li>Join a waiting slot with <strong>/ws/join-slot?slot_id=1&amp;model_name=name&amp;username=owner</strong>.</li>
            <li>Send moves as <strong>{"{ type: 'move', payload: { q, r } }"}</strong>.</li>
            <li>Player goals are red/player_1 left-to-right and blue/player_2 top-to-bottom.</li>
            <li>Rejected moves return <strong>move_rejected</strong>; accepted moves are broadcast to both players.</li>
          </ul>
        </article>

        <article className="docs-card">
          <span className="docs-icon">
            <Database className="h-5 w-5" />
          </span>
          <h2>6. Run your own server</h2>
          <p>Local server installation is optional. Start FastAPI locally, then point clients at <strong>ws://localhost:8000</strong> with <strong>--server</strong>. Use Redis for shared active slot/session state and PostgreSQL for completed-series history when needed.</p>
          <pre>
            <code>{`python -m uvicorn app.main:app --port 8000
python -m examples.hex_client --model-name model_my_agent --server ws://localhost:8000

HEX_STATE_BACKEND=redis
HEX_REDIS_URL=redis://localhost:6379/0
HEX_DATABASE_URL=postgresql+asyncpg://hexgame:hexgame@localhost:5432/hexgame
docker compose up --build`}</code>
          </pre>
        </article>
      </section>
    </main>
  );
}

function PlayerList({ slot }: { slot: SlotSnapshot }) {
  if (!slot.players.length) {
    return <span>None</span>;
  }

  return (
    <span className="grid gap-1">
      {slot.players.map((player) => (
        <span key={player}>
          {player}
          {slot.player_models?.[String(player)] ? (
            <span className="text-slate-500"> · {slot.player_models[String(player)]}</span>
          ) : null}
          {slot.player_usernames?.[String(player)] ? (
            <span className="text-slate-500"> · @{slot.player_usernames[String(player)]}</span>
          ) : null}
        </span>
      ))}
    </span>
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

  const currentPath = window.location.pathname.replace(/\/$/, "") || "/";
  const isOverviewPage = currentPath === "/overview";
  const isDocsPage = currentPath === "/docs";

  if (isDocsPage) {
    return <DocsPage />;
  }

  if (!isOverviewPage) {
    return (
      <main id="top" className="min-h-screen">
        <LandingPage totals={totals} />
      </main>
    );
  }

  return (
    <OverviewPage
      slots={slots}
      totals={totals}
      updatedAt={updatedAt}
      error={error}
      isLoading={isLoading}
      refresh={refresh}
    />
  );
}
