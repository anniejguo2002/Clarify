// Clarify frontend — vanilla JS, no build step.
// State is intentionally simple: one fetch returns all three reading modes
// (original/clear/simpler) up front, so switching modes afterwards is a
// pure client-side render with no network round-trip.

const homeView = document.getElementById("home-view");
const loadingView = document.getElementById("loading-view");
const readerView = document.getElementById("reader-view");

const inputForm = document.getElementById("input-form");
const inputText = document.getElementById("input-text");
const submitBtn = document.getElementById("submit-btn");
const homeError = document.getElementById("home-error");

const articleTitle = document.getElementById("article-title");
const articleBody = document.getElementById("article-body");
const articleSource = document.getElementById("article-source");
const articleEl = document.getElementById("article");

const modeToggle = document.getElementById("mode-toggle");
const spacingToggle = document.getElementById("spacing-toggle");
const textSizeInput = document.getElementById("text-size");
const focusToggle = document.getElementById("focus-toggle");
const backBtn = document.getElementById("back-btn");

let currentData = null;   // last successful /api/transform response
let currentMode = "clear";
let focusObserver = null;

function showView(view) {
  [homeView, loadingView, readerView].forEach((v) => (v.hidden = v !== view));
}

// Escape any raw HTML from the model/source text, then turn **bold** into
// <strong>. This keeps us safe from injection while still allowing the
// one bit of "rich text" the LLM is asked to produce.
function mdBoldToHtml(text) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderBlocks(blocks) {
  const frag = document.createDocumentFragment();
  blocks.forEach((block) => {
    if (block.type === "heading") {
      const h = document.createElement("h2");
      h.innerHTML = mdBoldToHtml(block.text || "");
      frag.appendChild(h);
    } else if (block.type === "bullets") {
      const ul = document.createElement("ul");
      (block.items || []).forEach((item) => {
        const li = document.createElement("li");
        li.innerHTML = mdBoldToHtml(item);
        ul.appendChild(li);
      });
      frag.appendChild(ul);
    } else {
      const p = document.createElement("p");
      p.innerHTML = mdBoldToHtml(block.text || "");
      frag.appendChild(p);
    }
  });
  return frag;
}

function renderOriginal(original) {
  const frag = document.createDocumentFragment();
  (original.paragraphs || []).forEach((text) => {
    const p = document.createElement("p");
    p.textContent = text;
    frag.appendChild(p);
  });
  return frag;
}

function renderMode(mode) {
  currentMode = mode;
  articleBody.innerHTML = "";

  if (mode === "original") {
    articleTitle.textContent = currentData.original.title || "Original text";
    articleBody.appendChild(renderOriginal(currentData.original));
  } else {
    const versionData = currentData[mode];
    articleTitle.textContent = currentData.title || currentData.original.title || "";
    articleBody.appendChild(renderBlocks(versionData.blocks || []));
  }

  document.querySelectorAll("#mode-toggle .segmented-btn").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.mode === mode);
  });

  setupFocusObserver();
}

function setupFocusObserver() {
  if (focusObserver) {
    focusObserver.disconnect();
    focusObserver = null;
  }
  if (!articleEl.classList.contains("focus-on")) return;

  const blocks = Array.from(articleBody.children);
  blocks.forEach((el) => el.classList.remove("is-focused"));
  if (blocks.length === 0) return;

  focusObserver = new IntersectionObserver(
    (entries) => {
      // Pick the entry closest to the vertical center of the viewport.
      let best = null;
      let bestDist = Infinity;
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const rect = entry.boundingClientRect;
        const center = rect.top + rect.height / 2;
        const dist = Math.abs(center - window.innerHeight / 2);
        if (dist < bestDist) {
          bestDist = dist;
          best = entry.target;
        }
      });
      if (best) {
        blocks.forEach((el) => el.classList.toggle("is-focused", el === best));
      }
    },
    { threshold: 0.15, rootMargin: "-20% 0px -20% 0px" }
  );
  blocks.forEach((el) => focusObserver.observe(el));
  blocks[0].classList.add("is-focused");
}

// ---- Home form submit ----
inputForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const value = inputText.value.trim();
  homeError.hidden = true;
  if (!value) {
    homeError.textContent = "Please paste a URL or some text first.";
    homeError.hidden = false;
    return;
  }

  submitBtn.disabled = true;
  document.getElementById("loading-text").textContent =
    /^https?:\/\//i.test(value)
      ? "Fetching the page and rewriting it…"
      : "Rewriting your text…";
  showView(loadingView);

  try {
    const res = await fetch("/api/transform", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");

    currentData = data;
    articleSource.hidden = !data.source_url;
    if (data.source_url) articleSource.textContent = data.source_url;

    showView(readerView);
    renderMode("clear");
  } catch (err) {
    showView(homeView);
    homeError.textContent = err.message || "Something went wrong. Please try again.";
    homeError.hidden = false;
  } finally {
    submitBtn.disabled = false;
  }
});

// ---- Mode toggle ----
modeToggle.addEventListener("click", (e) => {
  const btn = e.target.closest(".segmented-btn");
  if (!btn || !currentData) return;
  renderMode(btn.dataset.mode);
});

// ---- Spacing toggle ----
spacingToggle.addEventListener("click", (e) => {
  const btn = e.target.closest(".segmented-btn");
  if (!btn) return;
  document
    .querySelectorAll("#spacing-toggle .segmented-btn")
    .forEach((b) => b.classList.toggle("is-active", b === btn));
  articleEl.classList.remove("spacing-normal", "spacing-wide");
  articleEl.classList.add(`spacing-${btn.dataset.spacing}`);
});

// ---- Text size ----
textSizeInput.addEventListener("input", () => {
  for (let i = 0; i <= 4; i++) articleEl.classList.remove(`text-size-${i}`);
  articleEl.classList.add(`text-size-${textSizeInput.value}`);
});

// ---- Focus mode ----
focusToggle.addEventListener("click", () => {
  const isOn = focusToggle.getAttribute("aria-checked") === "true";
  focusToggle.setAttribute("aria-checked", String(!isOn));
  articleEl.classList.toggle("focus-on", !isOn);
  setupFocusObserver();
});

// ---- Back to home ----
backBtn.addEventListener("click", () => {
  currentData = null;
  inputText.value = "";
  showView(homeView);
});
