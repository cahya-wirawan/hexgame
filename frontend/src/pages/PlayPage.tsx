import { Bot, Gamepad2, Loader2, RefreshCw, Swords, Trophy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "../components/ui/button";
import { HexBoard } from "../components/HexBoard";
import { useHexGame } from "../hooks/useHexGame";
import { useDqnBot, type BotMode } from "../hooks/useDqnBot";
import { useAlphaZeroBot } from "../hooks/useAlphaZeroBot";

type WaitingSlot = {
  slot_id: number;
  board_size: number;
  series_length: number | null;
  player_models: Record<string, string>;
  player_usernames: Record<string, string>;
};

const BOARD_SIZES = [7, 9, 11, 13, 19] as const;
const SERIES_LENGTHS = [1, 3, 5, 7] as const;

function playerLabel(player: number, models: Record<string, string>, usernames: Record<string, string>) {
  const model = models[String(player)];
  const user  = usernames[String(player)];
  if (user && model && model !== "human") return `${model} @${user}`;
  if (user) return user;
  if (model) return model;
  return player === -1 ? "Red" : "Blue";
}

function colorOf(player: number) {
  return player === -1 ? "text-red-600" : "text-blue-600";
}

function swatchOf(player: number) {
  return player === -1 ? "bg-red-500" : "bg-blue-500";
}

function slotOpponentLabel(slot: WaitingSlot): string {
  const u = slot.player_usernames["-1"];
  const m = slot.player_models["-1"];
  if (u && m && m !== "human") return `${m} @${u}`;
  if (u) return u;
  if (m) return m;
  return "Anonymous";
}

const DQN_SIZES = [5, 7, 9, 11, 13] as const;
const AZ_SIZES  = [5, 7, 9, 11] as const;

const BOT_MODES: { mode: BotMode; label: string; detail: string }[] = [
  { mode: "dqn",     label: "DQN",      detail: "greedy best move" },
  { mode: "minimax", label: "Minimax",   detail: "α-β, 2-ply" },
  { mode: "mcts",    label: "MCTS",      detail: "200 sims, PUCT" },
];

// -1 = PLAYER_1 (red) starts; 1 = PLAYER_2 (blue) starts; 0 = random (resolved client-side)
type FirstPlayerChoice = -1 | 1 | 0;

function resolveFirstPlayer(choice: FirstPlayerChoice): number {
  if (choice === 0) return Math.random() < 0.5 ? -1 : 1;
  return choice;
}

function Lobby({
  onJoin,
  onJoinSlot,
  onPlayVsDqn,
  onPlayVsAZ,
  dqnLoading,
  azLoading,
}: {
  onJoin: (username: string, boardSize: number, seriesLength: number, firstPlayer: number) => void;
  onJoinSlot: (username: string, slotId: number) => void;
  onPlayVsDqn: (username: string, boardSize: number, mode: BotMode, seriesLength: number, firstPlayer: number) => void;
  onPlayVsAZ: (username: string, boardSize: number, seriesLength: number, firstPlayer: number, nSims: number) => void;
  dqnLoading: boolean;
  azLoading: boolean;
}) {
  const [username, setUsername] = useState("");
  const [boardSize, setBoardSize] = useState<number>(7);
  const [seriesLength, setSeriesLength] = useState<number>(1);
  const [firstPlayerChoice, setFirstPlayerChoice] = useState<FirstPlayerChoice>(-1);
  const [dqnBoardSize, setDqnBoardSize] = useState<number>(7);
  const [dqnSeriesLength, setDqnSeriesLength] = useState<number>(1);
  const [botMode, setBotMode] = useState<BotMode>("dqn");
  const [dqnFirstPlayer, setDqnFirstPlayer] = useState<FirstPlayerChoice>(-1);
  const [azBoardSize, setAzBoardSize] = useState<number>(7);
  const [azSeriesLength, setAzSeriesLength] = useState<number>(1);
  const [azFirstPlayer, setAzFirstPlayer] = useState<FirstPlayerChoice>(-1);
  const [azNSims, setAzNSims] = useState<number>(100);
  const [waitingSlots, setWaitingSlots] = useState<WaitingSlot[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function fetchSlots() {
      try {
        const res = await fetch("/slots");
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as Array<{
          slot_id: number;
          state: string;
          board_size: number | null;
          series_length: number | null;
          player_models: Record<string, string>;
          player_usernames: Record<string, string>;
        }>;
        if (!cancelled) {
          setWaitingSlots(
            data
              .filter((s) => s.state === "waiting" && s.board_size != null)
              .map((s) => ({
                slot_id: s.slot_id,
                board_size: s.board_size as number,
                series_length: s.series_length,
                player_models: s.player_models,
                player_usernames: s.player_usernames,
              }))
          );
        }
      } catch {
        // ignore fetch errors — server may not be up yet
      }
    }
    void fetchSlots();
    const id = setInterval(() => void fetchSlots(), 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="play-lobby">
      <div className="play-lobby-card">
        <span className="docs-icon">
          <Gamepad2 className="h-5 w-5" />
        </span>
        <h2>Play Hex in your browser</h2>
        <p>Challenge a waiting player or join matchmaking to be paired automatically.</p>

        <label className="play-label">
          Your name
          <input
            className="play-input"
            type="text"
            placeholder="anonymous"
            value={username}
            maxLength={40}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>

        {waitingSlots.length > 0 && (
          <div className="play-slot-picker">
            <p className="play-slot-picker-label">
              <Swords className="h-3.5 w-3.5" />
              Challenge a waiting player
            </p>
            <ul className="play-slot-list">
              {waitingSlots.map((slot) => (
                <li key={slot.slot_id} className="play-slot-row">
                  <div className="play-slot-info">
                    <span className="play-slot-opponent">{slotOpponentLabel(slot)}</span>
                    <span className="play-slot-meta">
                      {slot.board_size}×{slot.board_size}
                      {slot.series_length && slot.series_length > 1 ? ` · Bo${slot.series_length}` : ""}
                      {" · slot "}{slot.slot_id}
                    </span>
                  </div>
                  <Button
                    className="play-slot-btn"
                    onClick={() => onJoinSlot(username.trim() || "anonymous", slot.slot_id)}
                  >
                    <Swords className="h-3.5 w-3.5" />
                    Challenge
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="play-dqn-section">
          <p className="play-slot-picker-label">
            <Bot className="h-3.5 w-3.5" />
            Play vs DQN Bot (local AI)
          </p>
          <p className="play-dqn-desc">
            Runs the model in your browser — no server bot needed. First move may pause briefly while the model loads (~2–7 MB).
          </p>
          <div className="play-dqn-mode-row">
            {BOT_MODES.map(({ mode, label, detail }) => (
              <label key={mode} className={`play-dqn-mode-chip ${botMode === mode ? "play-dqn-mode-chip-active" : ""}`}>
                <input type="radio" name="bot_mode" value={mode} checked={botMode === mode} onChange={() => setBotMode(mode)} />
                <span className="play-dqn-mode-label">{label}</span>
                <span className="play-dqn-mode-detail">{detail}</span>
              </label>
            ))}
          </div>
          <div className="play-dqn-config">
            <fieldset className="play-fieldset">
              <legend className="play-label">Board size</legend>
              <div className="play-chips play-chips-compact">
                {DQN_SIZES.map((s) => (
                  <label key={s} className={`play-chip ${dqnBoardSize === s ? "play-chip-active" : ""}`}>
                    <input type="radio" name="dqn_board_size" value={s} checked={dqnBoardSize === s} onChange={() => setDqnBoardSize(s)} />
                    {s}×{s}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="play-fieldset">
              <legend className="play-label">Series</legend>
              <div className="play-chips play-chips-compact">
                {SERIES_LENGTHS.map((l) => (
                  <label key={l} className={`play-chip ${dqnSeriesLength === l ? "play-chip-active" : ""}`}>
                    <input type="radio" name="dqn_series_length" value={l} checked={dqnSeriesLength === l} onChange={() => setDqnSeriesLength(l)} />
                    Bo{l}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="play-fieldset">
              <legend className="play-label">Starts first</legend>
              <div className="play-chips play-chips-compact">
                {([[-1, "Bot (red)"], [1, "Me (blue)"], [0, "Random"]] as [FirstPlayerChoice, string][]).map(([v, label]) => (
                  <label key={v} className={`play-chip ${dqnFirstPlayer === v ? "play-chip-active" : ""}`}>
                    <input type="radio" name="dqn_first_player" value={v} checked={dqnFirstPlayer === v} onChange={() => setDqnFirstPlayer(v)} />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          <Button
            className="play-dqn-btn"
            onClick={() => onPlayVsDqn(username.trim() || "anonymous", dqnBoardSize, botMode, dqnSeriesLength, resolveFirstPlayer(dqnFirstPlayer))}
            disabled={dqnLoading}
          >
            {dqnLoading ? (
              <><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading…</>
            ) : (
              <><Bot className="h-3.5 w-3.5" />Play vs {BOT_MODES.find(m => m.mode === botMode)?.label ?? "DQN"}</>
            )}
          </Button>
        </div>

        <div className="play-az-section">
          <p className="play-slot-picker-label">
            <Bot className="h-3.5 w-3.5" />
            Play vs AlphaZero Bot (local AI)
          </p>
          <p className="play-az-desc">
            ResNet + MCTS, trained by self-play. Runs fully in your browser (~6 MB model, 100 simulations per move).
          </p>
          <div className="play-dqn-config">
            <fieldset className="play-fieldset">
              <legend className="play-label">Board size</legend>
              <div className="play-chips play-chips-compact">
                {AZ_SIZES.map((s) => (
                  <label key={s} className={`play-chip ${azBoardSize === s ? "play-chip-active" : ""}`}>
                    <input type="radio" name="az_board_size" value={s} checked={azBoardSize === s} onChange={() => setAzBoardSize(s)} />
                    {s}×{s}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="play-fieldset">
              <legend className="play-label">Series</legend>
              <div className="play-chips play-chips-compact">
                {SERIES_LENGTHS.map((l) => (
                  <label key={l} className={`play-chip ${azSeriesLength === l ? "play-chip-active" : ""}`}>
                    <input type="radio" name="az_series_length" value={l} checked={azSeriesLength === l} onChange={() => setAzSeriesLength(l)} />
                    Bo{l}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="play-fieldset">
              <legend className="play-label">Starts first</legend>
              <div className="play-chips play-chips-compact">
                {([[-1, "Bot (red)"], [1, "Me (blue)"], [0, "Random"]] as [FirstPlayerChoice, string][]).map(([v, label]) => (
                  <label key={v} className={`play-chip ${azFirstPlayer === v ? "play-chip-active" : ""}`}>
                    <input type="radio" name="az_first_player" value={v} checked={azFirstPlayer === v} onChange={() => setAzFirstPlayer(v)} />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="play-fieldset">
              <legend className="play-label">Strength (sims/move)</legend>
              <div className="play-chips play-chips-compact">
                {([25, 50, 100, 200, 400] as const).map((n) => (
                  <label key={n} className={`play-chip ${azNSims === n ? "play-chip-active" : ""}`}>
                    <input type="radio" name="az_n_sims" value={n} checked={azNSims === n} onChange={() => setAzNSims(n)} />
                    {n}
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          <Button
            className="play-az-btn"
            onClick={() => onPlayVsAZ(username.trim() || "anonymous", azBoardSize, azSeriesLength, resolveFirstPlayer(azFirstPlayer), azNSims)}
            disabled={azLoading}
          >
            {azLoading ? (
              <><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading…</>
            ) : (
              <><Bot className="h-3.5 w-3.5" />Play vs AlphaZero</>
            )}
          </Button>
        </div>

        <div className="play-form">
          <p className="play-form-divider-label">
            {waitingSlots.length > 0 ? "Or join matchmaking" : "Join matchmaking"}
          </p>

          <fieldset className="play-fieldset">
            <legend className="play-label">Board size</legend>
            <div className="play-chips">
              {BOARD_SIZES.map((s) => (
                <label key={s} className={`play-chip ${boardSize === s ? "play-chip-active" : ""}`}>
                  <input type="radio" name="board_size" value={s} checked={boardSize === s} onChange={() => setBoardSize(s)} />
                  {s}×{s}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="play-fieldset">
            <legend className="play-label">Series length</legend>
            <div className="play-chips">
              {SERIES_LENGTHS.map((l) => (
                <label key={l} className={`play-chip ${seriesLength === l ? "play-chip-active" : ""}`}>
                  <input type="radio" name="series_length" value={l} checked={seriesLength === l} onChange={() => setSeriesLength(l)} />
                  Best of {l}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="play-fieldset">
            <legend className="play-label">Starts game 1</legend>
            <div className="play-chips">
              {([[-1, "Red (default)"], [1, "Blue"], [0, "Random"]] as [FirstPlayerChoice, string][]).map(([v, label]) => (
                <label key={v} className={`play-chip ${firstPlayerChoice === v ? "play-chip-active" : ""}`}>
                  <input type="radio" name="first_player" value={v} checked={firstPlayerChoice === v} onChange={() => setFirstPlayerChoice(v)} />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          <Button
            className="play-join-btn"
            onClick={() => onJoin(username.trim() || "anonymous", boardSize, seriesLength, resolveFirstPlayer(firstPlayerChoice))}
          >
            <Gamepad2 className="h-4 w-4" />
            Join matchmaking
          </Button>
        </div>
      </div>

      <div className="play-rules">
        <h3>How to play</h3>
        <ul>
          <li><span className="inline-block w-3 h-3 rounded-sm bg-red-500 mr-1" /> Red connects <strong>left ↔ right</strong></li>
          <li><span className="inline-block w-3 h-3 rounded-sm bg-blue-500 mr-1" /> Blue connects <strong>top ↔ bottom</strong></li>
          <li>Click an empty cell on your turn to place a stone.</li>
          <li>The first player to form an unbroken chain wins the game.</li>
        </ul>
      </div>
    </div>
  );
}

export function PlayPage() {
  const { state, join, joinSlot, sendMove, reconnect, reset } = useHexGame();
  const { phase: botPhase, slotId: botSlotId, start: startBot, stop: stopBot } = useDqnBot();
  const { phase: azPhase, slotId: azSlotId, start: startAZ, stop: stopAZ } = useAlphaZeroBot();
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [isBotGame, setIsBotGame] = useState(false);
  const pendingBotJoin = useRef<{ username: string } | null>(null);
  const didAutoReconnect = useRef(false);

  useEffect(() => {
    if (didAutoReconnect.current) return;
    didAutoReconnect.current = true;

    const slotId = sessionStorage.getItem("hex_slot_id");
    const token  = sessionStorage.getItem("hex_token");
    if (slotId && token) {
      setIsReconnecting(true);
      reconnect(Number(slotId), token);
    }
  }, [reconnect]);

  // Clear reconnecting flag once we leave the waiting phase
  useEffect(() => {
    if (state.phase !== "waiting") setIsReconnecting(false);
  }, [state.phase]);

  // Once the DQN bot has a slot, have the human join it
  useEffect(() => {
    if (!isBotGame || !botSlotId || !pendingBotJoin.current) return;
    const { username } = pendingBotJoin.current;
    pendingBotJoin.current = null;
    joinSlot(username, botSlotId);
  }, [isBotGame, botSlotId, joinSlot]);

  // Once the AlphaZero bot has a slot, have the human join it
  useEffect(() => {
    if (!isBotGame || !azSlotId || !pendingBotJoin.current) return;
    const { username } = pendingBotJoin.current;
    pendingBotJoin.current = null;
    joinSlot(username, azSlotId);
  }, [isBotGame, azSlotId, joinSlot]);

  const handlePlayVsDqn = async (username: string, boardSize: number, mode: BotMode, seriesLength: number, firstPlayer: number) => {
    setIsBotGame(true);
    pendingBotJoin.current = { username };
    try {
      await startBot(boardSize, mode, seriesLength, firstPlayer);
    } catch {
      setIsBotGame(false);
      pendingBotJoin.current = null;
    }
  };

  const handlePlayVsAZ = async (username: string, boardSize: number, seriesLength: number, firstPlayer: number, nSims: number) => {
    setIsBotGame(true);
    pendingBotJoin.current = { username };
    try {
      await startAZ(boardSize, seriesLength, firstPlayer, nSims);
    } catch {
      setIsBotGame(false);
      pendingBotJoin.current = null;
    }
  };

  const handleReset = () => {
    reset();
    stopBot();
    stopAZ();
    setIsBotGame(false);
    pendingBotJoin.current = null;
  };

  const { phase, board, boardSize, myPlayer, currentTurn, winner, seriesWinner,
          player1Wins, player2Wins, seriesLength, winsRequired, currentGame,
          playerModels, playerUsernames, errorMessage, slotId } = state;

  const isMyTurn = currentTurn === myPlayer;
  const myColor = myPlayer !== null ? (myPlayer === -1 ? "Red" : "Blue") : null;

  function turnBanner() {
    if (phase === "game_over") {
      const w = winner!;
      return (
        <div className={`play-banner play-banner-${w === -1 ? "red" : "blue"}`}>
          <Trophy className="h-4 w-4" />
          {playerLabel(w, playerModels, playerUsernames)} wins game {currentGame}!
          {seriesLength > 1 && ` — Score: ${player1Wins}-${player2Wins} (need ${winsRequired})`}
          <span className="play-banner-sub">Waiting for next game…</span>
        </div>
      );
    }
    if (isMyTurn) {
      return <div className="play-banner play-banner-your-turn">Your turn ({myColor})</div>;
    }
    return (
      <div className="play-banner play-banner-wait">
        {playerLabel(currentTurn!, playerModels, playerUsernames)}'s turn — waiting…
      </div>
    );
  }

  if (phase === "lobby") {
    return (
      <main className="play-shell">
        <PlayNav onReset={handleReset} />
        <Lobby
          onJoin={join}
          onJoinSlot={joinSlot}
          onPlayVsDqn={(u, s, m, sl, fp) => void handlePlayVsDqn(u, s, m, sl, fp)}
          onPlayVsAZ={(u, s, sl, fp, ns) => void handlePlayVsAZ(u, s, sl, fp, ns)}
          dqnLoading={botPhase === "loading" || botPhase === "connecting"}
          azLoading={azPhase === "loading" || azPhase === "connecting"}
        />
      </main>
    );
  }

  if (phase === "waiting") {
    return (
      <main className="play-shell">
        <PlayNav onReset={handleReset} />
        <div className="play-waiting">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-600" />
          {isReconnecting ? (
            <>
              <p>Reconnecting to game in slot {slotId}…</p>
              <p className="play-waiting-sub">Your seat is held for a short window after disconnect.</p>
            </>
          ) : (
            <>
              <p>Waiting for an opponent on {boardSize}×{boardSize} board…</p>
              <p className="play-waiting-sub">Open another browser tab or run <code>hexgame play</code> to join.</p>
            </>
          )}
          <Button onClick={handleReset} className="mt-4">Cancel</Button>
        </div>
      </main>
    );
  }

  if (phase === "series_over") {
    const sw = seriesWinner!;
    return (
      <main className="play-shell">
        <PlayNav onReset={handleReset} />
        <div className="play-series-over">
          <Trophy className={`h-12 w-12 ${colorOf(sw)}`} />
          <h2 className={colorOf(sw)}>{playerLabel(sw, playerModels, playerUsernames)} wins the series!</h2>
          <p>Final score: {player1Wins}–{player2Wins}</p>
          {board && (
            <div className="play-board-wrapper play-board-final">
              <HexBoard
                board={board} boardSize={boardSize} myPlayer={myPlayer}
                currentTurn={null} winner={winner}
                onCellClick={() => undefined} disabled
              />
            </div>
          )}
          <Button onClick={handleReset}>Play again</Button>
        </div>
      </main>
    );
  }

  if (phase === "error" || !board) {
    return (
      <main className="play-shell">
        <PlayNav onReset={handleReset} />
        <div className="play-error">
          <p>{errorMessage ?? "Connection error"}</p>
          <Button onClick={handleReset}><RefreshCw className="h-4 w-4" /> Back to lobby</Button>
        </div>
      </main>
    );
  }

  return (
    <main className="play-shell">
      <PlayNav onReset={handleReset} />

      <div className="play-game-layout">
        <aside className="play-sidebar">
          <section className="play-info-card">
            <h3>Players</h3>
            {([-1, 1] as const).map((p) => {
              const active = currentTurn === p && phase === "playing";
              return (
                <div key={p} className={`play-player-row ${active ? "play-player-active" : ""}`}>
                  <span className={`play-swatch ${swatchOf(p)}`} />
                  <span className="play-player-name">
                    {playerLabel(p, playerModels, playerUsernames)}
                    {p === myPlayer && <span className="play-you-badge">you</span>}
                  </span>
                  {seriesLength > 1 && (
                    <span className="play-score">{p === -1 ? player1Wins : player2Wins}</span>
                  )}
                </div>
              );
            })}
          </section>

          <section className="play-info-card">
            <h3>Match</h3>
            <dl className="play-meta">
              <dt>Board</dt><dd>{boardSize}×{boardSize}</dd>
              <dt>Series</dt><dd>Best of {seriesLength}</dd>
              {seriesLength > 1 && <><dt>Game</dt><dd>{currentGame}</dd></>}
              {seriesLength > 1 && <><dt>Score</dt><dd>{player1Wins}–{player2Wins}</dd></>}
              {seriesLength > 1 && <><dt>Need</dt><dd>{winsRequired} win{winsRequired > 1 ? "s" : ""}</dd></>}
            </dl>
          </section>

          <section className="play-info-card">
            <h3>Goal</h3>
            <ul className="play-goal-list">
              <li><span className="play-swatch bg-red-500" /> Red: left ↔ right</li>
              <li><span className="play-swatch bg-blue-500" /> Blue: top ↔ bottom</li>
            </ul>
          </section>

          {errorMessage && (
            <div className="play-inline-error">{errorMessage}</div>
          )}
        </aside>

        <div className="play-board-area">
          {turnBanner()}
          <div className="play-board-wrapper">
            <HexBoard
              board={board}
              boardSize={boardSize}
              myPlayer={myPlayer}
              currentTurn={currentTurn}
              winner={winner}
              onCellClick={(r, q) => sendMove(q, r)}
              disabled={phase !== "playing"}
            />
          </div>
        </div>
      </div>
    </main>
  );
}

function PlayNav({ onReset }: { onReset: () => void }) {
  return (
    <nav className="docs-nav play-nav">
      <a className="brand-mark overview-brand" href="/" aria-label="Home">
        <span className="brand-glyph">H</span>
        <span>Hex Game Server</span>
      </a>
      <div className="nav-links">
        <a href="/play" className="font-bold">Play</a>
        <a href="/overview">Slots</a>
        <a href="/statistics">Stats</a>
        <a href="/docs">Docs</a>
      </div>
      <button className="play-nav-reset" onClick={onReset} title="Back to lobby">
        <RefreshCw className="h-4 w-4" />
      </button>
    </nav>
  );
}
