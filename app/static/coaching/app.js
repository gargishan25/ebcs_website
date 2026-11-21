/* EBCS Coaching - interface behaviour. No dependencies. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const typing = (el) => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

  /* ------------------------------------------------ command palette --- */
  const back = $("#cx-pal");
  const dataEl = $("#cx-pal-data");
  if (back && dataEl) {
    const items = JSON.parse(dataEl.textContent || "[]");
    const input = $("input", back);
    const list = $("ul", back);
    let shown = [], idx = 0;

    const score = (item, q) => {
      if (!q) return 1;
      const hay = (item.label + " " + (item.group || "") + " " + (item.keys || "")).toLowerCase();
      let s = 0, pos = 0;
      for (const ch of q) {
        const f = hay.indexOf(ch, pos);
        if (f < 0) return 0;
        s += f === pos ? 2 : 1;
        pos = f + 1;
      }
      if (hay.startsWith(q)) s += 5;
      return s;
    };
    const render = () => {
      const q = input.value.trim().toLowerCase();
      shown = items.map((it) => [score(it, q), it]).filter((x) => x[0] > 0)
        .sort((a, b) => b[0] - a[0]).slice(0, 12).map((x) => x[1]);
      idx = Math.min(idx, Math.max(0, shown.length - 1));
      list.innerHTML = shown.length ? shown.map((it, i) =>
        `<li class="${i === idx ? "on" : ""}"><a href="${it.href}">${it.label.replace(/</g, "&lt;")}<span class="grp">${it.group || ""}</span></a></li>`
      ).join("") : `<li><a class="muted">No matches</a></li>`;
    };
    const open = () => { back.classList.add("open"); input.value = ""; idx = 0; render(); setTimeout(() => input.focus(), 10); };
    const close = () => back.classList.remove("open");
    window.cxOpenPalette = open;

    $$("[data-open-palette]").forEach((b) => b.addEventListener("click", open));
    back.addEventListener("click", (e) => { if (e.target === back) close(); });
    input.addEventListener("input", () => { idx = 0; render(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { idx = Math.min(idx + 1, shown.length - 1); render(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { idx = Math.max(idx - 1, 0); render(); e.preventDefault(); }
      else if (e.key === "Enter" && shown[idx]) { location.href = shown[idx].href; }
      else if (e.key === "Escape") close();
    });

    /* global shortcuts: Cmd/Ctrl+K, "/", and g-then-letter */
    let gPending = 0;
    const jumps = {};
    items.forEach((it) => { if (it.jump) jumps[it.jump] = it.href; });
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); back.classList.contains("open") ? close() : open(); return; }
      if (typing(document.activeElement) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") { e.preventDefault(); open(); return; }
      if (e.key === "g") { gPending = Date.now(); return; }
      if (gPending && Date.now() - gPending < 900 && jumps[e.key]) { location.href = jumps[e.key]; }
      gPending = 0;
    });
  }

  /* ---------------------------------------------------- mobile side --- */
  const side = $(".cx-side");
  $$("[data-toggle-side]").forEach((b) => b.addEventListener("click", () => side && side.classList.toggle("open")));

  /* ---------------------------------------------------------- toasts --- */
  $$(".toast").forEach((t, i) => {
    const kill = () => { t.style.transition = "opacity .2s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 220); };
    $("button", t) && $("button", t).addEventListener("click", kill);
    if (!t.classList.contains("error")) setTimeout(kill, 5200 + i * 400);
  });

  /* --------------------------------------------------------- confirm --- */
  document.addEventListener("submit", (e) => {
    const msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /* ------------------------------------------------------- row links --- */
  $$("tr[data-href]").forEach((tr) => {
    tr.classList.add("rowlink");
    tr.addEventListener("click", (e) => { if (!e.target.closest("a,button,input,label,form")) location.href = tr.dataset.href; });
  });

  /* ------------------------------------------------------ countdowns --- */
  const tick = () => {
    $$("[data-countdown]").forEach((el) => {
      const t = Date.parse(el.dataset.countdown);
      if (isNaN(t)) return;
      let s = Math.round((t - Date.now()) / 1000);
      if (s <= 0) { el.textContent = s > -3600 ? "happening now" : "started"; return; }
      const d = Math.floor(s / 86400); s -= d * 86400;
      const h = Math.floor(s / 3600); s -= h * 3600;
      const m = Math.floor(s / 60);
      el.textContent = "in " + (d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`);
    });
  };
  tick(); setInterval(tick, 30000);

  /* ----------------------------------------------------- bulk select --- */
  $$("[data-check-all]").forEach((all) => {
    const form = all.closest("form");
    const boxes = () => $$("[data-check-item]", form);
    const counter = $("[data-check-count]", form);
    const sync = () => {
      const n = boxes().filter((b) => b.checked).length;
      if (counter) counter.textContent = n ? `${n} selected` : "";
      $$("[data-needs-selection]", form).forEach((b) => (b.disabled = !n));
    };
    all.addEventListener("change", () => { boxes().forEach((b) => (b.checked = all.checked)); sync(); });
    form.addEventListener("change", (e) => { if (e.target.matches("[data-check-item]")) sync(); });
    sync();
  });

  /* ----------------------------------------------- availability grid --- */
  $$(".avail[data-paint]").forEach((grid) => {
    const cells = $$(".avail-cell input", grid);
    const count = $("[data-avail-count]", grid);
    let painting = null;
    const sync = () => { if (count) count.textContent = `${cells.filter((c) => c.checked).length} h / week`; };
    const set = (inp, v) => { if (inp && inp.checked !== v) inp.checked = v; };
    const cellAt = (x, y) => { const el = document.elementFromPoint(x, y); return el && el.closest(".avail-cell") && $("input", el.closest(".avail-cell")); };

    grid.addEventListener("pointerdown", (e) => {
      const inp = e.target.closest(".avail-cell") && $("input", e.target.closest(".avail-cell"));
      if (!inp) return;
      e.preventDefault();
      painting = !inp.checked;
      set(inp, painting); sync();
      try { grid.setPointerCapture(e.pointerId); } catch (_) { /* synthetic or already released */ }
    });
    grid.addEventListener("pointermove", (e) => { if (painting === null) return; set(cellAt(e.clientX, e.clientY), painting); sync(); });
    const stop = () => { painting = null; };
    grid.addEventListener("pointerup", stop); grid.addEventListener("pointercancel", stop);
    cells.forEach((c) => c.addEventListener("click", (e) => e.preventDefault())); // pointer handles toggling
    cells.forEach((c) => c.addEventListener("keydown", (e) => { if (e.key === " ") { e.preventDefault(); c.checked = !c.checked; sync(); } }));

    $$("[data-preset]", grid).forEach((b) => b.addEventListener("click", () => {
      const p = b.dataset.preset;
      cells.forEach((c) => {
        const [d, h] = c.value.split("-").map(Number);
        if (p === "clear") c.checked = false;
        if (p === "evenings" && d < 5 && h >= 16 && h <= 19) c.checked = true;
        if (p === "weekends" && d >= 5 && h >= 10 && h <= 16) c.checked = true;
      });
      sync();
    }));
    sync();
  });

  /* --------------------------------------------- sign-up form extras --- */
  const form = $(".cx-form[data-signup]");
  if (form) {
    const minorBands = (form.dataset.minor || "").split(",");
    const syncMinor = () => {
      const v = ($("input[name=age_band]:checked", form) || {}).value;
      form.classList.toggle("is-minor", minorBands.includes(v));
    };
    $$("input[name=age_band]", form).forEach((r) => r.addEventListener("change", syncMinor));
    syncMinor();

    const links = $$(".cx-form-nav a");
    if ("IntersectionObserver" in window && links.length) {
      const io = new IntersectionObserver((ents) => {
        ents.forEach((en) => {
          if (!en.isIntersecting) return;
          links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + en.target.id));
        });
      }, { rootMargin: "-40% 0px -55% 0px" });
      $$(".sec", form).forEach((s) => io.observe(s));
    }
  }

  /* ---------------------------------------------------------- thread --- */
  const th = $(".thread");
  if (th) th.scrollTop = th.scrollHeight;
  const comp = $(".composer textarea");
  if (comp) {
    comp.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); comp.form.requestSubmit(); }
    });
    comp.addEventListener("input", () => { comp.style.height = "40px"; comp.style.height = Math.min(comp.scrollHeight, 180) + "px"; });
  }

  /* ------------------------------------------- session-form prefill --- */
  const pairSel = $("select[data-format-map]");
  if (pairSel) {
    const map = JSON.parse(pairSel.dataset.formatMap);
    const fmt = $("select[name=format]");
    pairSel.addEventListener("change", () => { if (map[pairSel.value] && fmt) fmt.value = map[pairSel.value]; });
  }
})();
