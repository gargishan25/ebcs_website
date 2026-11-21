/* EBCS Coaching - chess board.
 *
 *   <div data-board data-fen="..." data-solution="Rd8# / Re8"></div>   interactive (puzzle if solution)
 *   <div data-board-mini data-fen="..."></div>                         static thumbnail
 *
 * Rules come from chess.js (loaded from jsDelivr). If that can't load, the
 * board still renders the position read-only, so lessons never break.
 */
const GLYPH = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const VS = "︎"; // force text presentation (stops iOS turning pawns into emoji)
const FILES = "abcdefgh";

function parseFen(fen) {
  const rows = (fen || "").split(" ")[0].split("/");
  const grid = [];
  for (let r = 0; r < 8; r++) {
    const row = [];
    for (const ch of rows[r] || "8") {
      if (/\d/.test(ch)) for (let i = 0; i < +ch; i++) row.push(null);
      else row.push({ type: ch.toLowerCase(), color: ch === ch.toUpperCase() ? "w" : "b" });
    }
    while (row.length < 8) row.push(null);
    grid.push(row.slice(0, 8));
  }
  while (grid.length < 8) grid.push(Array(8).fill(null));
  return grid; // grid[0] = rank 8
}
const turnOf = (fen) => ((fen || "").split(" ")[1] === "b" ? "b" : "w");
const sqName = (r, f) => FILES[f] + (8 - r);

function draw(el, grid, opts = {}) {
  const flip = !!opts.flip;
  const board = document.createElement("div");
  board.className = "board" + (opts.readonly ? " ro" : "");
  for (let i = 0; i < 64; i++) {
    const vr = Math.floor(i / 8), vf = i % 8;
    const r = flip ? 7 - vr : vr, f = flip ? 7 - vf : vf;
    const name = sqName(r, f);
    const sq = document.createElement("div");
    sq.className = "sq " + ((r + f) % 2 ? "d" : "l");
    sq.dataset.sq = name;
    if (opts.last && (opts.last.from === name || opts.last.to === name)) sq.classList.add("last");
    if (opts.sel === name) sq.classList.add("sel");
    if (opts.targets && opts.targets[name] !== undefined) {
      sq.classList.add("tgt");
      if (opts.targets[name]) sq.classList.add("cap");
    }
    if (opts.check === name) sq.classList.add("check");
    if (!opts.mini) {
      if (vr === 7) sq.insertAdjacentHTML("beforeend", `<span class="co f">${FILES[f]}</span>`);
      if (vf === 0) sq.insertAdjacentHTML("beforeend", `<span class="co r">${8 - r}</span>`);
    }
    const pc = grid[r][f];
    if (pc) sq.insertAdjacentHTML("beforeend", `<span class="pc ${pc.color}" data-c="${pc.color}">${GLYPH[pc.type]}${VS}</span>`);
    board.appendChild(sq);
  }
  el.replaceChildren(board);
  return board;
}

/* ---------------------------------------------------------------- mini --- */
document.querySelectorAll("[data-board-mini]").forEach((el) => {
  el.classList.add("mini-board");
  draw(el, parseFen(el.dataset.fen), { readonly: true, mini: true, flip: turnOf(el.dataset.fen) === "b" });
});

/* --------------------------------------------------------- interactive --- */
const hosts = Array.from(document.querySelectorAll("[data-board]"));
if (hosts.length) {
  // Show the position straight away; make it playable once the rules load.
  hosts.forEach((host) => {
    host.classList.add("board-wrap");
    const holder = document.createElement("div");
    host.replaceChildren(holder);
    draw(holder, parseFen(host.dataset.fen), { readonly: true, flip: turnOf(host.dataset.fen) === "b" });
  });
  let Chess = null;
  try {
    const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 8000));
    ({ Chess } = await Promise.race([import("https://cdn.jsdelivr.net/npm/chess.js@1/+esm"), timeout]));
  } catch (e) {
    console.warn("chess.js unavailable, boards are read-only", e);
  }
  hosts.forEach((host) => mount(host, Chess));
}

function mount(host, Chess) {
  const startFen = host.dataset.fen;
  const accepted = (host.dataset.solution || "").split(/[\s,/|]+/).map((s) => s.replace(/[+#!?]/g, "")).filter(Boolean);
  const isPuzzle = accepted.length > 0;
  host.classList.add("board-wrap");
  const surface = document.createElement("div");
  const bar = document.createElement("div");
  bar.className = "board-bar";
  const status = document.createElement("div");
  status.className = "board-status";
  const moves = document.createElement("div");
  moves.className = "movelist";
  host.replaceChildren(surface, status, bar, moves);

  let flip = turnOf(startFen) === "b";

  if (!Chess) {
    draw(surface, parseFen(startFen), { readonly: true, flip });
    status.textContent = "Board is view-only right now (couldn't load move rules).";
    return;
  }

  let game;
  try { game = new Chess(startFen); } catch (e) {
    draw(surface, parseFen(startFen), { readonly: true, flip });
    status.textContent = "This position isn't valid, so moves are disabled.";
    return;
  }

  let sel = null, targets = null, last = null, solved = false, lock = false;
  const call = (a, b) => (typeof game[a] === "function" ? game[a]() : game[b]());

  const kingSquare = (color) => {
    const b = game.board();
    for (let r = 0; r < 8; r++) for (let f = 0; f < 8; f++) {
      const p = b[r][f];
      if (p && p.type === "k" && p.color === color) return sqName(r, f);
    }
  };
  const turnText = () => {
    const side = game.turn() === "w" ? "White" : "Black";
    if (call("isCheckmate", "in_checkmate")) return `Checkmate. ${side === "White" ? "Black" : "White"} wins.`;
    if (call("isStalemate", "in_stalemate")) return "Stalemate.";
    if (call("isDraw", "in_draw")) return "Draw.";
    return `<span class="turn-dot ${game.turn()}"></span> ${side} to move` + (call("inCheck", "in_check") ? " - check" : "");
  };

  const render = () => {
    const grid = game.board().map((row) => row.map((p) => (p ? { type: p.type, color: p.color } : null)));
    const check = call("inCheck", "in_check") ? kingSquare(game.turn()) : null;
    draw(surface, grid, { flip, sel, targets, last, check });
    if (!lock && !status.dataset.sticky) status.innerHTML = isPuzzle && !solved
      ? `${turnText()}. Find the best move.` : turnText();
    const h = game.history();
    moves.textContent = h.length ? h.map((m, i) => (i % 2 === 0 ? `${Math.floor(i / 2) + 1}. ` : "") + m).join(" ") : "";
  };

  const legalFrom = (sq) => {
    const out = {};
    game.moves({ square: sq, verbose: true }).forEach((m) => { out[m.to] = !!m.captured; });
    return out;
  };

  const tryMove = (from, to) => {
    let mv = null;
    try { mv = game.move({ from, to, promotion: "q" }); } catch (e) { mv = null; }
    sel = null; targets = null;
    if (!mv) { render(); return false; }
    last = { from: mv.from, to: mv.to };
    if (isPuzzle && !solved && game.history().length === 1) {
      const ok = accepted.includes(mv.san.replace(/[+#]/g, "")) || call("isCheckmate", "in_checkmate");
      if (ok) {
        solved = true;
        status.dataset.sticky = "1";
        status.className = "board-status ok";
        status.textContent = `Correct: ${mv.san}. Keep exploring, or reset to try again.`;
        host.dispatchEvent(new CustomEvent("board:solved", { bubbles: true }));
      } else {
        lock = true;
        status.className = "board-status no";
        status.textContent = `${mv.san} isn't it. Look again: checks, captures, threats.`;
        render();
        setTimeout(() => { game.undo(); last = null; lock = false; status.className = "board-status"; render(); }, 900);
        return true;
      }
    }
    render();
    return true;
  };

  /* pointer: click-click and drag */
  let drag = null;
  surface.addEventListener("pointerdown", (e) => {
    if (lock) return;
    const sqEl = e.target.closest(".sq");
    if (!sqEl) return;
    const sq = sqEl.dataset.sq;
    const piece = game.get(sq);
    if (sel && targets && targets[sq] !== undefined) { tryMove(sel, sq); return; }
    if (piece && piece.color === game.turn()) {
      sel = sq; targets = legalFrom(sq); render();
      const pcEl = surface.querySelector(`.sq[data-sq="${sq}"] .pc`);
      if (pcEl) {
        const rect = pcEl.getBoundingClientRect();
        const ghost = pcEl.cloneNode(true);
        Object.assign(ghost.style, { position: "fixed", pointerEvents: "none", zIndex: 99, left: rect.left + "px", top: rect.top + "px",
          width: rect.width + "px", textAlign: "center", fontSize: getComputedStyle(pcEl).fontSize, cursor: "grabbing" });
        drag = { from: sq, ghost, dx: e.clientX - rect.left, dy: e.clientY - rect.top, moved: false, src: pcEl };
        surface.setPointerCapture(e.pointerId);
      }
    } else { sel = null; targets = null; render(); }
  });
  surface.addEventListener("pointermove", (e) => {
    if (!drag) return;
    if (!drag.moved) { document.body.appendChild(drag.ghost); drag.src.style.opacity = ".25"; drag.moved = true; }
    drag.ghost.style.left = e.clientX - drag.dx + "px";
    drag.ghost.style.top = e.clientY - drag.dy + "px";
  });
  surface.addEventListener("pointerup", (e) => {
    if (!drag) return;
    const d = drag; drag = null;
    if (!d.moved) return;
    d.ghost.remove();
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const target = el && el.closest && el.closest(".sq");
    if (target && target.dataset.sq !== d.from && targets && targets[target.dataset.sq] !== undefined) tryMove(d.from, target.dataset.sq);
    else render();
  });

  const btn = (label, fn, cls = "btn btn-sm") => {
    const b = document.createElement("button");
    b.type = "button"; b.className = cls; b.textContent = label; b.addEventListener("click", fn);
    bar.appendChild(b); return b;
  };
  btn("Reset", () => { game.load(startFen); sel = targets = last = null; solved = false; delete status.dataset.sticky; status.className = "board-status"; render(); });
  btn("Undo", () => { if (game.undo()) { last = null; render(); } });
  btn("Flip", () => { flip = !flip; render(); });
  if (isPuzzle && host.dataset.solutionText) {
    const reveal = btn("Show answer", () => { reveal.replaceWith(Object.assign(document.createElement("span"), { className: "small muted", textContent: "Answer: " + host.dataset.solutionText })); }, "btn btn-sm btn-ghost");
  }
  btn("Copy FEN", (ev) => {
    navigator.clipboard && navigator.clipboard.writeText(game.fen());
    ev.target.textContent = "Copied"; setTimeout(() => (ev.target.textContent = "Copy FEN"), 1200);
  }, "btn btn-sm btn-ghost");
  render();
}
