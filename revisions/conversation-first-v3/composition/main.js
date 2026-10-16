/* v3 · Conversation first — deterministic paused GSAP timelines seeked per frame.
   Only two supplements; everything else is live conversation (plus the native source insert). */
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
  const GOLD = "#e2b55a", RED = "#e5533d", SLATE = "#8fa3b6";

  // Gauge arcs (upper semicircle, centre 540,960, radius 360).
  const arc = (a0, a1) => {
    const p = (a) => [540 + 360 * Math.cos(a * Math.PI / 180), 960 + 360 * Math.sin(a * Math.PI / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M${x0.toFixed(1)} ${y0.toFixed(1)} A360 360 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
  };
  const arcL = mk("path", { d: arc(181, 238), stroke: RED }, $("#s7arcs"));
  const arcM = mk("path", { d: arc(242, 298), stroke: GOLD }, $("#s7arcs"));
  const arcR = mk("path", { d: arc(302, 359), stroke: SLATE }, $("#s7arcs"));

  // Fix transform origins once (no smooth-origin compensation -> reverse-seek deterministic).
  gsap.set("#s4card, #s7healthy", { transformOrigin: "50% 50%", smoothOrigin: false });
  gsap.set("#s7needle", { transformOrigin: "50% 100%", smoothOrigin: false });

  const T = () => gsap.timeline({ paused: true, defaults: { ease: "power2.out" } });
  const scenes = [];
  const scene = (id, start, end, tl) => scenes.push({ el: $(id), start, end, tl });
  const inOut = (tl, el, dur) => {
    tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, ease: "none" }, 0);
    tl.fromTo(el, { opacity: 1 }, { opacity: 0, duration: 0.2, ease: "none", immediateRender: false }, dur - 0.2);
  };

  // Supplement 1: 14.565-18.765 (local 0-4.2). Words: push 14.64, follow 16.95, inversion 18.25.
  {
    const d = 4.2, tl = T();
    inOut(tl, "#s4", d);
    tl.fromTo("#s4h", { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0.0);
    tl.fromTo("#s4card", { y: -30, opacity: 0, rotation: 0 }, { y: 0, opacity: 1, duration: 0.35 }, 0.0);
    tl.fromTo("#s4check", { opacity: 1 }, { opacity: 1, duration: 0.01 }, 0);
    tl.fromTo("#s4q", { opacity: 0 }, { opacity: 0, duration: 0.01 }, 0);
    tl.fromTo("#s4badge", { attr: { fill: GOLD } }, { attr: { fill: GOLD }, duration: 0.01 }, 0);
    // 1 PUSH BACK: the confident check becomes a question.
    tl.fromTo("#s4t1", { x: -60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.35 }, 0.1);
    tl.to("#s4check", { opacity: 0, duration: 0.15 }, 0.55);
    tl.to("#s4q", { opacity: 1, duration: 0.2 }, 0.6);
    tl.to("#s4badge", { attr: { fill: RED }, duration: 0.25 }, 0.55);
    // 2 FOLLOW UP
    tl.fromTo("#s4t2", { x: -60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.35 }, 2.35);
    // 3 INVERT: the answer is turned over.
    tl.fromTo("#s4t3", { x: -60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.35 }, 3.62);
    tl.to("#s4card", { rotation: 180, duration: 0.45, ease: "power2.inOut" }, 3.68);
    scene("#s4", 14.565, 18.765, tl);
  }

  // Supplement 2: 31.930-35.000 (local 0-3.07). Words: always 31.93, healthy 33.16, skepticism 33.87-34.51.
  {
    const d = 3.07, tl = T();
    inOut(tl, "#s7", d);
    tl.fromTo("#s7h", { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.3 }, 0.0);
    tl.fromTo("#s7needle", { rotation: -70 }, { rotation: 60, duration: 0.8, ease: "power2.inOut" }, 0.15);
    tl.to("#s7needle", { rotation: 0, duration: 0.5, ease: "back.out(1.8)" }, 0.95);
    tl.fromTo([arcL, arcR], { opacity: 0.9 }, { opacity: 0.3, duration: 0.3 }, 1.2);
    tl.fromTo(arcM, { opacity: 0.45 }, { opacity: 1, duration: 0.3 }, 1.2);
    tl.fromTo("#s7healthy", { opacity: 0, scale: 0.7 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(1.8)" }, 1.25);
    scene("#s7", 31.93, 35.0, tl);
  }

  window.renderFrame = (t) => {
    for (const s of scenes) {
      const on = t >= s.start && t < s.end;
      s.el.style.visibility = on ? "visible" : "hidden";
      s.tl.seek(0, false);
      s.tl.seek(on ? t - s.start : 0, false);
      if (!on) s.el.style.opacity = "0";
    }
  };
  window.renderFrame(0);
})();
