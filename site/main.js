// Sublease Matchmaker landing page: small, dependency-free interactions.
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const wait = (ms) => new Promise((r) => setTimeout(r, reduce ? 0 : ms));

// ---- nav: translucent after scrolling, menu on small screens ----
const nav = $("#nav");
const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
onScroll();
window.addEventListener("scroll", onScroll, { passive: true });

const toggle = $(".nav-toggle");
const links = $("#nav-links");
toggle.addEventListener("click", () => {
  const open = toggle.getAttribute("aria-expanded") !== "true";
  toggle.setAttribute("aria-expanded", String(open));
  links.classList.toggle("open", open);
});
links.addEventListener("click", (e) => {
  if (e.target.closest("a")) { toggle.setAttribute("aria-expanded", "false"); links.classList.remove("open"); }
});

// Placeholder links (the Discord invite) shouldn't jump to the top.
$$('[data-placeholder="discord-invite"]').forEach((a) => a.addEventListener("click", (e) => {
  if (a.getAttribute("href") === "#") e.preventDefault();
}));

// ---- reveal on scroll ----
const io = new IntersectionObserver((entries) => entries.forEach((en) => {
  if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
}), { threshold: 0.15 });
$$(".reveal").forEach((el) => io.observe(el));

// ---- hero: the DM plays in once ----
const dmMsgs = $$("#hero-dm .msg");
const dmObs = new IntersectionObserver(async ([en]) => {
  if (!en.isIntersecting) return;
  dmObs.disconnect();
  for (const m of dmMsgs) { m.classList.add("in"); await wait(m.classList.contains("me") ? 650 : 900); }
}, { threshold: 0.3 });
dmObs.observe($("#hero-dm"));

// ---- how it works: steps drive the stage ----
const steps = $$(".step");
const panels = $$(".panel");
function showStep(i) {
  steps.forEach((s, k) => s.classList.toggle("is-active", k === i));
  panels.forEach((p, k) => p.classList.toggle("show", k === i));
}
showStep(0);
// On narrow screens each step shows its own picture inline (CSS hides the side stage).
steps.forEach((s, i) => {
  const copy = panels[i].cloneNode(true);
  copy.className = "step-panel";
  copy.setAttribute("aria-hidden", "true");
  s.appendChild(copy);
});
steps.forEach((s, i) => {
  s.tabIndex = 0;
  s.addEventListener("click", () => showStep(i));
  s.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showStep(i); } });
});
const stepObs = new IntersectionObserver((entries) => entries.forEach((en) => {
  if (en.isIntersecting && window.innerWidth > 900) showStep(Number(en.target.dataset.step));
}), { rootMargin: "-45% 0px -45% 0px" });
steps.forEach((s) => stepObs.observe(s));

// ---- signature: replay a real negotiation on the rent rail ----
const MIN = 700, MAX = 950;
const pct = (v) => `${((v - MIN) / (MAX - MIN)) * 100}%`;
const arena = $(".arena");
const feed = $("#feed");
const mSun = $("#m-sun"), mPool = $("#m-pool"), mDeal = $("#m-deal");
const playBtn = $("#play");

$("#reveal-limits").addEventListener("change", (e) => arena.classList.toggle("reveal-on", e.target.checked));

const SCRIPT = [
  { side: "pool", who: "Alex's agent", what: "proposes <b>$780/mo</b> · Jun 1 → Aug 15 · deposit $300", rent: 780,
    msg: "Alex is interested in the furnished room for June 1 to Aug 15, at $780/month with utilities included. Happy with the non-smoking rule." },
  { side: "ref", who: "Referee", what: "removed a hint about date flexibility", msg: "The message went through without it." },
  { side: "sun", who: "Jordan's agent", what: "counters <b>$825/mo</b> · deposit $350", rent: 825,
    msg: "June 1 to Aug 15 works for us, and we can prorate the last days. We'd like to meet in the middle at $825/month." },
  { side: "pool", who: "Alex's agent", what: "accepts <b>$825/mo</b>",
    msg: "That works for us. We accept June 1 to Aug 15 at $825/month with a $350 deposit." },
  { side: "deal", who: "Deal", what: "<b>$825/mo</b> · ≈ $2,062 for the stay", msg: "Both students now get a Confirm button. Nothing is shared until both tap it." },
];

function resetRail() {
  feed.innerHTML = "";
  mSun.style.setProperty("--x", pct(850)); $(".m-val", mSun).textContent = "$850"; $(".m-who", mSun).textContent = "asking";
  mPool.classList.remove("on"); mDeal.classList.remove("on"); mSun.style.opacity = mPool.style.opacity = "";
}

let playing = false;
async function play() {
  if (playing) return;
  playing = true;
  playBtn.disabled = true;
  $("#feed-empty").hidden = true;
  resetRail();
  for (const t of SCRIPT) {
    await wait(t.side === "ref" ? 700 : 1100);
    const li = document.createElement("li");
    li.className = t.side;
    li.innerHTML = `<span class="who">${t.who}</span><span class="what">${t.what}</span><span class="msgtext">${t.msg}</span>`;
    feed.appendChild(li);
    if (t.side === "pool" && t.rent) {
      mPool.style.setProperty("--x", pct(t.rent)); $(".m-val", mPool).textContent = `$${t.rent}`; mPool.classList.add("on");
    }
    if (t.side === "sun" && t.rent) {
      mSun.style.setProperty("--x", pct(t.rent)); $(".m-val", mSun).textContent = `$${t.rent}`; $(".m-who", mSun).textContent = "counter";
    }
    if (t.side === "pool" && !t.rent) {
      mPool.style.setProperty("--x", pct(825));
    }
    if (t.side === "deal") {
      mDeal.style.setProperty("--x", pct(825)); mDeal.classList.add("on"); mSun.style.opacity = mPool.style.opacity = "0";
    }
  }
  playBtn.textContent = "↻ Replay";
  playBtn.disabled = false;
  playing = false;
}
playBtn.addEventListener("click", play);
// Play once by itself when the arena scrolls into view (not with reduced motion).
if (!reduce) {
  const arenaObs = new IntersectionObserver(([en]) => { if (en.isIntersecting) { arenaObs.disconnect(); play(); } }, { threshold: 0.5 });
  arenaObs.observe(arena);
}

// ---- privacy ladder: a segmented control over three stages ----
const tabs = $$('.seg [role="tab"]');
const ladder = $("#ladder");
const notes = [
  "Anyone on the server sees the neighborhood, dates and asking rent. No address, no names.",
  "While the agents negotiate, only offers and terms are exchanged. Still no names or address.",
  "After you both tap Confirm, you see each other's name and the full address in a private thread.",
];
function setStage(i) {
  tabs.forEach((t, k) => { t.setAttribute("aria-selected", String(k === i)); t.tabIndex = k === i ? 0 : -1; });
  $$(".field", ladder).forEach((f) => {
    if (f.classList.contains("never")) return;
    const hidden = Number(f.dataset.from) > i;
    f.classList.toggle("hidden", hidden);
    $("b", f).setAttribute("aria-hidden", String(hidden));
    if (!$(".lock", f)) f.insertAdjacentHTML("beforeend", '<span class="lock">🔒 Hidden at this stage</span>');
  });
  $("#ladder-note").textContent = notes[i];
}
setStage(0);
tabs.forEach((t, i) => {
  t.addEventListener("click", () => setStage(i));
  t.addEventListener("keydown", (e) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    const n = (i + d + tabs.length) % tabs.length;
    setStage(n); tabs[n].focus();
  });
});

// ---- problem: each pain point highlights its messages in the group chat ----
const gc = $(".gc");
const pains = $$(".pain");
let painTimer = null;
function focusPain(name) {
  pains.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pain === name)));
  if (name) gc.dataset.focus = name; else delete gc.dataset.focus;
}
function stopCycle() { clearInterval(painTimer); painTimer = null; }
pains.forEach((b) => {
  b.addEventListener("click", () => { stopCycle(); focusPain(b.getAttribute("aria-pressed") === "true" ? null : b.dataset.pain); });
  b.addEventListener("mouseenter", () => { stopCycle(); focusPain(b.dataset.pain); gc.classList.add("paused"); });
  b.addEventListener("mouseleave", () => gc.classList.remove("paused"));
});
if (!reduce) {
  // Until someone interacts, walk through the four pains on its own.
  const order = pains.map((b) => b.dataset.pain);
  let k = 0;
  const cycleObs = new IntersectionObserver(([en]) => {
    if (en.isIntersecting && !painTimer && !pains.some((b) => b.matches(":hover"))) {
      focusPain(order[k]);
      painTimer = setInterval(() => { k = (k + 1) % order.length; focusPain(order[k]); }, 2800);
    } else if (!en.isIntersecting) stopCycle();
  }, { threshold: 0.4 });
  cycleObs.observe($(".problem"));
}

// ---- safety: the checklist ticks itself off once it's on screen ----
const checks = $$(".viz-check li");
const checkObs = new IntersectionObserver(async ([en]) => {
  if (!en.isIntersecting) return;
  checkObs.disconnect();
  for (const li of checks) { await wait(450); li.classList.add("done"); }
}, { threshold: 0.6 });
checkObs.observe($(".t-check"));
