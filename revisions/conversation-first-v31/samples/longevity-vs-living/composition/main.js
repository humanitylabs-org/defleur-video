/* TSR Ep7 · "Longevity isn't the same as living" · v3.1 conversation first.
   Four sparse beats; everything else is the live conversation. Paused GSAP timelines are
   seeked per frame; text that depends on time is computed directly from t (no callbacks). */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s) => document.querySelector(s);
  const mk = (tag, attrs, parent) => {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  };
  const WHITE = "#f3ece2", DIM = "#6b6258", GOLD = "#e9b45c", RED = "#e5533d";
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const T = () => gsap.timeline({ paused: true, defaults: { ease: "power2.out" } });
  const scenes = [];
  const scene = (id, start, end, tl, apply) => scenes.push({ el: $(id), start, end, tl, apply });
  const fadeInOut = (tl, el, d) => {
    tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.25, ease: "none" }, 0);
    tl.fromTo(el, { opacity: 1 }, { opacity: 0, duration: 0.25, ease: "none", immediateRender: false }, d - 0.25);
  };
  const dashSetup = (el) => { const L = el.getTotalLength(); el.setAttribute("stroke-dasharray", L.toFixed(1)); return L; };

  /* ---------- Beat 1 · 3.45-7.95 (local 0-4.5) ----------
     "...thinking that they will live forever" (forever 3.96) / "I don't think that's psychologically healthy" (6.88-7.76). */
  {
    const d = 4.5, tl = T();
    const infL = dashSetup($("#b1inf"));
    gsap.set("#b1stamp", { transformOrigin: "50% 50%", smoothOrigin: false });
    fadeInOut(tl, "#b1", d);
    tl.fromTo("#b1h", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 0.0);
    // A finite lifeline: the END marker is pushed off the canvas and the line runs on past the edge.
    tl.fromTo("#b1end", { x: 0 }, { x: 560, duration: 0.95, ease: "power2.in" }, 0.5);
    tl.fromTo("#b1line", { attr: { x2: 800 } }, { attr: { x2: 1220 }, duration: 0.95, ease: "power2.in" }, 0.5);
    // ... and the infinity sign draws itself above it.
    tl.fromTo("#b1inf", { opacity: 0 }, { opacity: 1, duration: 0.05, ease: "none" }, 0.6);
    tl.fromTo("#b1inf", { attr: { "stroke-dashoffset": infL } }, { attr: { "stroke-dashoffset": 0 }, duration: 1.0, ease: "power1.inOut" }, 0.55);
    tl.fromTo("#b1inf", { attr: { stroke: GOLD } }, { attr: { stroke: GOLD }, duration: 0.01 }, 0);
    tl.fromTo("#b1line", { attr: { stroke: WHITE } }, { attr: { stroke: WHITE }, duration: 0.01 }, 0);
    // Verdict on "psychologically healthy": the forever-line turns red and the stamp lands.
    tl.to("#b1inf", { attr: { stroke: RED }, duration: 0.25 }, 3.4);
    tl.to("#b1line", { attr: { stroke: "#8a3b30" }, duration: 0.25 }, 3.4);
    tl.fromTo("#b1stamp", { opacity: 0, scale: 1.5, rotation: -14 }, { opacity: 1, scale: 1, rotation: -5, duration: 0.3, ease: "back.out(1.6)" }, 3.45);
    scene("#b1", 3.45, 7.95, tl);
  }

  /* ---------- Beat 2 · 15.85-27.45 (local 0-11.6) ----------
     every 15.94 · current one 18.34-18.86 · same meals 19.26-19.96 · bed at 8 30 20.66-21.68 · no exceptions 22.20-22.86
     really living 24.18-24.76 · sentence 26.18-26.50 */
  const b2 = { cells: [], plates: [], clocks: [] };
  {
    const grid = $("#b2grid");
    const W = 180, H = 135, G = 12, X0 = 162, Y0 = 410;
    for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) {
      const x = X0 + c * (W + G), y = Y0 + r * (H + G), cx = x + W / 2, cy = y + H / 2;
      const g = mk("g", {}, grid);
      mk("rect", { x, y, width: W, height: H, rx: 14, fill: "rgba(243,236,226,0.06)", stroke: "#5c544b", "stroke-width": 3 }, g);
      const plate = mk("g", {}, g);
      mk("circle", { cx: cx - 58, cy, r: 22, fill: "none", stroke: DIM, "stroke-width": 5 }, plate);
      mk("circle", { cx: cx - 58, cy, r: 10, fill: "none", stroke: DIM, "stroke-width": 3 }, plate);
      const clock = mk("text", { x: cx - 26, y: cy + 16, "text-anchor": "start", "font-size": 44, fill: DIM, class: "inter", "letter-spacing": 0 }, g);
      clock.textContent = "8:30";
      b2.cells.push(g); b2.plates.push(plate); b2.clocks.push(clock);
    }
    const bars = $("#b2bars");
    for (let i = 0; i < 7; i++) mk("rect", { x: 158 + i * 123, y: 380, width: 24, height: 660, rx: 6, fill: "url(#steel)" }, bars);
    mk("rect", { x: 150, y: 376, width: 780, height: 22, rx: 6, fill: "url(#steel)" }, bars);
    mk("rect", { x: 150, y: 1024, width: 780, height: 22, rx: 6, fill: "url(#steel)" }, bars);

    const d = 11.6, tl = T();
    fadeInOut(tl, "#b2", d);
    gsap.set(b2.cells, { transformOrigin: "50% 50%", smoothOrigin: false });
    // The current year copies itself, cell after cell, while the counter runs.
    b2.cells.forEach((g, i) => tl.fromTo(g, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.25, ease: "back.out(1.6)" }, 0.08 + i * 0.15));
    tl.fromTo("#b2hA", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.3 }, 0.0);
    // Same meals: every plate lights at once.
    b2.plates.forEach((p, i) => tl.fromTo(Array.from(p.children), { attr: { stroke: DIM } }, { attr: { stroke: GOLD }, duration: 0.2 }, 3.41 + (i % 4) * 0.03));
    tl.fromTo("#b2tagA", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3 }, 3.41);
    // Bed at 8:30: every clock lights.
    b2.clocks.forEach((k, i) => tl.fromTo(k, { attr: { fill: DIM } }, { attr: { fill: WHITE }, duration: 0.2 }, 4.85 + (i % 4) * 0.03));
    tl.fromTo("#b2tagB", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3 }, 4.85);
    // No exceptions: the two habits merge into one rule and all sixteen years pulse together.
    tl.to(["#b2tagA", "#b2tagB"], { opacity: 0, y: -24, duration: 0.25 }, 6.35);
    tl.fromTo("#b2tagC", { opacity: 0, scale: 0.8 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(1.6)" }, 6.4);
    tl.to(b2.cells, { scale: 1.07, duration: 0.18, ease: "power1.out" }, 6.45);
    tl.to(b2.cells, { scale: 1, duration: 0.25, ease: "power1.in" }, 6.63);
    // Really living?
    tl.to("#b2hA", { opacity: 0, y: -30, duration: 0.25 }, 8.3);
    tl.fromTo("#b2hB", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3 }, 8.33);
    // ...or a sentence: bars slam down over the identical years.
    tl.fromTo(Array.from(bars.children), { y: -1300 }, { y: 0, duration: 0.42, ease: "power3.in", stagger: 0.04 }, 9.95);
    tl.to(b2.cells, { opacity: 0.55, duration: 0.3 }, 10.35);
    tl.to("#b2tagC", { opacity: 0, duration: 0.25 }, 10.3);
    tl.to("#b2hB", { opacity: 0, y: -30, duration: 0.2 }, 10.3);
    gsap.set("#b2hC", { transformOrigin: "50% 50%", smoothOrigin: false });
    tl.fromTo("#b2hC", { opacity: 0, scale: 1.3 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(1.6)" }, 10.33);
    const year = (local) => {
      const p = clamp((local - 0.08) / 2.5, 0, 1);
      const n = Math.round(Math.pow(10, 4 * p));
      return "YEAR " + n.toLocaleString("en-US") + (p >= 1 ? "+" : "");
    };
    scene("#b2", 15.85, 27.45, tl, (local) => { $("#b2hA").textContent = year(local); });
    gsap.set(Array.from(bars.children), { y: -1300 });
  }

  /* ---------- Beat 3 · 35.70-41.80 (local 0-6.1) ----------
     purpose of life 34.47-35.44 · experience 35.86 · love 36.34 · integration 36.96 · chaos 37.52 · synthesize 40.08 */
  {
    const bars = $("#b3bars");
    for (let i = 0; i < 7; i++) mk("rect", { x: 158 + i * 123, y: 380, width: 24, height: 660, rx: 6, fill: "url(#steel)", opacity: 0.85 }, bars);
    const nodes = [
      { w: "EXPERIENCE", x: 330, y: 540, c: GOLD, t: 0.16 },
      { w: "LOVE", x: 775, y: 600, c: "#ef8a6e", t: 0.64 },
      { w: "INTEGRATION", x: 345, y: 930, c: "#8fb0de", t: 1.26 },
      { w: "CHAOS", x: 765, y: 990, c: "#c3a2e6", t: 1.82 },
    ];
    const links = $("#b3links"), nl = $("#b3nodes");
    const spokes = nodes.map((n) => mk("line", { x1: n.x, y1: n.y, x2: 540, y2: 760, stroke: n.c, "stroke-width": 8, "stroke-linecap": "round", opacity: 0.9 }, links));
    const ringOrder = [0, 1, 3, 2, 0];
    const ring = [];
    for (let i = 0; i < 4; i++) {
      const a = nodes[ringOrder[i]], b = nodes[ringOrder[i + 1]];
      ring.push(mk("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: "#cfc6b8", "stroke-width": 5, "stroke-linecap": "round", opacity: 0.7 }, links));
    }
    const groups = nodes.map((n) => {
      const g = mk("g", {}, nl);
      mk("circle", { cx: n.x, cy: n.y, r: 120, fill: n.c, opacity: 0.16 }, g);
      mk("circle", { cx: n.x, cy: n.y, r: 16, fill: n.c }, g);
      const t = mk("text", { x: n.x, y: n.y - 34, "text-anchor": "middle", "font-size": 64, fill: WHITE, class: "anton" }, g);
      t.textContent = n.w;
      return g;
    });
    const d = 6.1, tl = T();
    fadeInOut(tl, "#b3", d);
    gsap.set(groups, { transformOrigin: "50% 50%", smoothOrigin: false });
    gsap.set("#b3core", { svgOrigin: "540 760", smoothOrigin: false });
    tl.fromTo("#b3h", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.3 }, 0.0);
    // The rigid bars from the previous image lift away as the first word arrives.
    tl.fromTo(Array.from(bars.children), { y: 0 }, { y: -1300, duration: 0.6, ease: "power2.in", stagger: 0.04 }, 0.1);
    nodes.forEach((n, i) => tl.fromTo(groups[i], { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(1.8)" }, n.t));
    // Synthesize: each part is drawn into one centre, then the parts are tied to each other.
    spokes.forEach((s, i) => { const L = dashSetup(s); tl.fromTo(s, { opacity: 0 }, { opacity: 0.9, duration: 0.05, ease: "none" }, 4.3 + i * 0.06); tl.fromTo(s, { attr: { "stroke-dashoffset": L } }, { attr: { "stroke-dashoffset": 0 }, duration: 0.5, ease: "power1.inOut" }, 4.3 + i * 0.06); });
    tl.fromTo("#b3core", { opacity: 0, scale: 0.2 }, { opacity: 1, scale: 1, duration: 0.5, ease: "back.out(1.5)" }, 4.65);
    ring.forEach((s, i) => { const L = dashSetup(s); tl.fromTo(s, { opacity: 0 }, { opacity: 0.7, duration: 0.05, ease: "none" }, 5.0 + i * 0.08); tl.fromTo(s, { attr: { "stroke-dashoffset": L } }, { attr: { "stroke-dashoffset": 0 }, duration: 0.45, ease: "power1.inOut" }, 5.0 + i * 0.08); });
    scene("#b3", 35.7, 41.8, tl);
  }

  /* ---------- Beat 4 · 66.00-74.20 (local 0-8.2) ----------
     maximize 66.59 · overall average quality 67.65-69.77 · existence 70.59 · experience 72.41 · times 73.11 */
  {
    const marks = $("#b4marks");
    const cols = ["#f3d79a", "#ef8a6e", "#fff3dc", "#c98a4c", "#f3d79a", "#e9b45c"];
    const ms = [];
    for (let i = 0; i < 18; i++) {
      const x = 230 + ((i * 137) % 600), y = 560 + ((i * 211) % 440), w = 70 + ((i * 53) % 90);
      ms.push(mk("rect", { x, y, width: w, height: 16, rx: 8, fill: cols[i % cols.length], opacity: 0.85 }, marks));
    }
    const d = 8.2, tl = T();
    fadeInOut(tl, "#b4", d);
    gsap.set(["#b4alive", "#b4hC", "#b4time"], { transformOrigin: "50% 50%", smoothOrigin: false });
    gsap.set(ms, { transformOrigin: "0% 50%", smoothOrigin: false });
    tl.fromTo("#b4hA", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.3 }, 0.0);
    tl.fromTo("#b4secs", { opacity: 0 }, { opacity: 1, duration: 0.25 }, 0.05);
    tl.fromTo(["#b4yaxis", "#b4yarrow"], { opacity: 0.25 }, { opacity: 0.25, duration: 0.01 }, 0);
    // "Overall average quality": the thin line of seconds gains height and becomes an area.
    tl.to("#b4hA", { opacity: 0, y: -30, duration: 0.25 }, 1.6);
    tl.fromTo("#b4hB", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3 }, 1.65);
    tl.to("#b4secs", { opacity: 0, y: 40, duration: 0.3 }, 1.6);
    tl.to(["#b4yaxis", "#b4yarrow"], { opacity: 1, duration: 0.3 }, 1.65);
    tl.fromTo("#b4qual", { opacity: 0, x: -20 }, { opacity: 1, x: 0, duration: 0.3 }, 1.8);
    tl.fromTo("#b4rect", { attr: { y: 1044, height: 12 } }, { attr: { y: 500, height: 556 }, duration: 2.0, ease: "power2.inOut" }, 1.7);
    // "Existence and your experience": the area fills with lived moments.
    ms.forEach((m, i) => tl.fromTo(m, { opacity: 0, scaleX: 0 }, { opacity: 0.85, scaleX: 1, duration: 0.25 }, 4.6 + i * 0.11));
    // "Times the amount of time": the formula completes and the area is named.
    tl.to("#b4hB", { opacity: 0, y: -30, duration: 0.2 }, 7.05);
    tl.fromTo("#b4hC", { opacity: 0, scale: 1.2 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(1.6)" }, 7.1);
    tl.fromTo("#b4time", { scale: 1 }, { scale: 1.3, duration: 0.18 }, 7.1);
    tl.to("#b4time", { scale: 1, duration: 0.25 }, 7.28);
    tl.to(ms, { opacity: 0.35, duration: 0.3 }, 7.15);
    tl.fromTo("#b4alive", { opacity: 0, scale: 0.8 }, { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(1.6)" }, 7.2);
    scene("#b4", 66.0, 74.2, tl);
  }

  window.renderFrame = (t) => {
    for (const s of scenes) {
      const on = t >= s.start && t < s.end;
      const local = on ? t - s.start : 0;
      s.el.style.visibility = on ? "visible" : "hidden";
      s.tl.seek(0, false);
      s.tl.seek(local, false);
      if (s.apply) s.apply(local);
      if (!on) s.el.style.opacity = "0";
    }
  };
  window.renderFrame(0);
})();
