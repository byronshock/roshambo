// The page's half of the web game (roshambo/web.py). The game id lives only in this variable,
// never in a cookie or storage, so reloading the page starts a new game.
"use strict";

let game = null;
let busy = false;

const moves = [...document.querySelectorAll("button[data-move]")];
const newButton = document.getElementById("new");
const roundEl = document.getElementById("round");
const noteEl = document.getElementById("note");
const countEl = document.getElementById("count");
const scoreEl = {
  you: document.getElementById("you"),
  ties: document.getElementById("ties"),
  bot: document.getElementById("bot"),
};

const VERDICT = { win: "You win.", lose: "The bot wins.", tie: "A tie." };

function enable(on) {
  for (const b of moves) b.disabled = !on;
  newButton.disabled = !on;
}

function showScore(score, round) {
  for (const k of ["you", "ties", "bot"]) scoreEl[k].textContent = score[k];
  countEl.textContent = `Round ${round}`;
}

function showRound(data) {
  const verdict = document.createElement("span");
  verdict.className = data.result;
  verdict.textContent = VERDICT[data.result];
  roundEl.replaceChildren(`You played ${data.you}, the bot played ${data.bot}. `, verdict);
}

async function play(move) {
  if (busy) return;
  busy = true;
  enable(false);
  try {
    const res = await fetch("/api/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game, move }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    const lost = data.new && game !== null;
    game = data.over ? null : data.game;
    showRound(data);
    showScore(data.score, data.round);
    if (data.over) {
      noteEl.textContent = `That's ${data.round} rounds, the end of this game. Your next move starts a new one.`;
    } else if (lost) {
      noteEl.textContent = "The server had let your last game go, so this is a new one.";
    } else {
      noteEl.textContent = "";
    }
  } catch {
    noteEl.textContent = "Couldn't reach the bot. Try that move again.";
  } finally {
    busy = false;
    enable(true);
  }
}

function newGame() {
  game = null;
  roundEl.textContent = "Your move.";
  noteEl.textContent = "";
  showScore({ you: 0, ties: 0, bot: 0 }, 0);
}

for (const b of moves) b.addEventListener("click", () => play(b.dataset.move));
newButton.addEventListener("click", newGame);

document.addEventListener("keydown", (e) => {
  if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
  const key = (e.key || "").toLowerCase();
  if (key === "r" || key === "p" || key === "s") {
    e.preventDefault();
    play(key);
  }
});

enable(true);
