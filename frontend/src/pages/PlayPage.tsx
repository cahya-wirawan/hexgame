import { Gamepad2, Loader2, RefreshCw, Trophy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "../components/ui/button";
import { HexBoard } from "../components/HexBoard";
import { useHexGame } from "../hooks/useHexGame";

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

function Lobby({ onJoin }: { onJoin: (username: string, boardSize: number, seriesLength: number) => void }) {
  const [username, setUsername] = useState("");
  const [boardSize, setBoardSize] = useState<number>(7);
  const [seriesLength, setSeriesLength] = useState<number>(1);

  return (
    <div className="play-lobby">
      <div className="play-lobby-card">
        <span className="docs-icon">
          <Gamepad2 className="h-5 w-5" />
        </span>
        <h2>Play Hex in your browser</h2>
        <p>Join matchmaking and wait for an opponent — another browser tab, CLI bot, or anyone connected to this server.</p>

        <div className="play-form">
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

          <Button
            className="play-join-btn"
            onClick={() => onJoin(username.trim() || "anonymous", boardSize, seriesLength)}
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
  const { state, join, sendMove, reconnect, reset } = useHexGame();
  const [isReconnecting, setIsReconnecting] = useState(false);
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
        <PlayNav onReset={reset} />
        <Lobby onJoin={join} />
      </main>
    );
  }

  if (phase === "waiting") {
    return (
      <main className="play-shell">
        <PlayNav onReset={reset} />
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
          <Button onClick={reset} className="mt-4">Cancel</Button>
        </div>
      </main>
    );
  }

  if (phase === "series_over") {
    const sw = seriesWinner!;
    return (
      <main className="play-shell">
        <PlayNav onReset={reset} />
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
          <Button onClick={reset}>Play again</Button>
        </div>
      </main>
    );
  }

  if (phase === "error" || !board) {
    return (
      <main className="play-shell">
        <PlayNav onReset={reset} />
        <div className="play-error">
          <p>{errorMessage ?? "Connection error"}</p>
          <Button onClick={reset}><RefreshCw className="h-4 w-4" /> Back to lobby</Button>
        </div>
      </main>
    );
  }

  return (
    <main className="play-shell">
      <PlayNav onReset={reset} />

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
