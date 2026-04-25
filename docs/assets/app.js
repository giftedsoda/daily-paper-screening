/* Awesome Papers — dashboard app */

const state = {
  papers: [],
  facetKeys: [],       // discovered from data, e.g. ["category", "task", "modality"]
  active: {},          // facetKey -> Set of selected values
  yearActive: new Set(),
  keywordActive: new Set(),
  has_code: false,
  has_venue: false,
  query: "",
  sort: "date-desc",
  settings: {
    keywords: [],
    facets: [],
  },
};

/* Color index for each facet (cycles through CSS --tag-N-* vars) */
const facetColorIndex = {};

// ---------- boot ----------
init().catch((err) => {
  document.getElementById("result-count").textContent =
    "Failed to load papers.json — " + err.message;
  console.error(err);
});

async function init() {
  const res = await fetch("data/papers.json");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  state.papers = data.papers || [];

  discoverFacets();
  loadSettingsFromURL();
  resolveRepoLink();
  buildSidebar();
  bindSidebarControls();
  bindTopbar();
  bindSettings();
  render();
}

function discoverFacets() {
  const keySet = new Set();
  for (const p of state.papers) {
    if (!p.tags) continue;
    for (const k of Object.keys(p.tags)) keySet.add(k);
  }
  state.facetKeys = [...keySet];
  let idx = 0;
  for (const k of state.facetKeys) {
    state.active[k] = new Set();
    facetColorIndex[k] = idx % 8;
    idx++;
  }
}

function resolveRepoLink() {
  const m = location.hostname.match(/^([^.]+)\.github\.io$/);
  const parts = location.pathname.split("/").filter(Boolean);
  if (m && parts.length) {
    document.getElementById("gh-link").href =
      `https://github.com/${m[1]}/${parts[0]}`;
  }
}

// ---------- sidebar ----------
function buildSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const yearGroup = sidebar.querySelector('[data-facet="year"]');

  // Remove any previously inserted dynamic facet groups
  sidebar.querySelectorAll(".filter-group[data-dynamic]").forEach((el) => el.remove());

  // Keywords filter group (at the top, before tag facets)
  if (state.settings.keywords.length) {
    const kwGroup = document.createElement("div");
    kwGroup.className = "filter-group";
    kwGroup.dataset.facet = "_keyword";
    kwGroup.dataset.dynamic = "true";
    kwGroup.innerHTML = `<h3>Keywords</h3><div class="facet-options"></div>`;
    sidebar.insertBefore(kwGroup, yearGroup);

    const kwContainer = kwGroup.querySelector(".facet-options");
    for (const kw of state.settings.keywords) {
      const kwLower = kw.toLowerCase();
      const count = state.papers.filter((p) => {
        const hay = [p.title, p.abstract || "", p.venue, p.authors, p.notes].join(" ").toLowerCase();
        return hay.includes(kwLower);
      }).length;
      const label = document.createElement("label");
      label.className = "chk";
      label.innerHTML = `
        <input type="checkbox" data-facet="_keyword" data-value="${esc(kw)}">
        ${esc(kw)}
        <span class="count">${count}</span>
      `;
      kwContainer.appendChild(label);
      label.querySelector("input").addEventListener("change", (e) => {
        if (e.target.checked) state.keywordActive.add(kw);
        else state.keywordActive.delete(kw);
        render();
      });
    }
  }

  // Insert dynamic facet groups before the year group
  const settingKeys = new Set(state.settings.facets.map((f) => f.key));
  for (const key of state.facetKeys) {
    if (settingKeys.size && !settingKeys.has(key)) continue;
    const group = document.createElement("div");
    group.className = "filter-group";
    group.dataset.facet = key;
    group.dataset.dynamic = "true";
    group.innerHTML = `<h3>${formatLabel(key)}</h3><div class="facet-options"></div>`;
    sidebar.insertBefore(group, yearGroup);

    const container = group.querySelector(".facet-options");
    const counts = tallyFacet(key);
    const values = [...counts.keys()].sort();
    for (const v of values) {
      const label = document.createElement("label");
      label.className = "chk";
      label.innerHTML = `
        <input type="checkbox" data-facet="${key}" data-value="${esc(v)}">
        ${esc(v)}
        <span class="count">${counts.get(v)}</span>
      `;
      container.appendChild(label);
      label.querySelector("input").addEventListener("change", onFacetChange);
    }
  }

  // Year facet
  const yearContainer = yearGroup.querySelector(".facet-options");
  yearContainer.innerHTML = "";
  const yearCounts = new Map();
  for (const p of state.papers) {
    if (!p.year) continue;
    yearCounts.set(p.year, (yearCounts.get(p.year) || 0) + 1);
  }
  const years = [...yearCounts.keys()].sort((a, b) => b - a);
  for (const y of years) {
    const label = document.createElement("label");
    label.className = "chk";
    label.innerHTML = `
      <input type="checkbox" data-facet="year" data-value="${y}">
      ${y}
      <span class="count">${yearCounts.get(y)}</span>
    `;
    yearContainer.appendChild(label);
    label.querySelector("input").addEventListener("change", onFacetChange);
  }

}

/* Bind sidebar controls that should only attach once */
let sidebarBound = false;
function bindSidebarControls() {
  if (sidebarBound) return;
  sidebarBound = true;

  document.querySelectorAll("[data-extra]").forEach((el) => {
    el.addEventListener("change", () => {
      state[el.dataset.extra] = el.checked;
      render();
    });
  });

  document.getElementById("clear-filters").addEventListener("click", () => {
    for (const k of state.facetKeys) state.active[k].clear();
    state.yearActive.clear();
    state.keywordActive.clear();
    state.has_code = false;
    state.has_venue = false;
    document
      .querySelectorAll(".sidebar input[type=checkbox]")
      .forEach((el) => (el.checked = false));
    document.getElementById("search").value = "";
    state.query = "";
    render();
  });
}

function formatLabel(key) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function tallyFacet(key) {
  const counts = new Map();
  for (const p of state.papers) {
    const v = p.tags ? p.tags[key] : undefined;
    if (!v) continue;
    if (Array.isArray(v)) {
      for (const x of v) counts.set(x, (counts.get(x) || 0) + 1);
    } else {
      counts.set(v, (counts.get(v) || 0) + 1);
    }
  }
  return counts;
}

function onFacetChange(e) {
  const { facet, value } = e.target.dataset;
  if (facet === "year") {
    const y = Number(value);
    if (e.target.checked) state.yearActive.add(y);
    else state.yearActive.delete(y);
  } else {
    const set = state.active[facet];
    if (e.target.checked) set.add(value);
    else set.delete(value);
  }
  render();
}

// ---------- topbar ----------
function bindTopbar() {
  const search = document.getElementById("search");
  search.addEventListener("input", () => {
    state.query = search.value.trim().toLowerCase();
    render();
  });
  document.getElementById("sort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    render();
  });
}

// ---------- filtering / sorting ----------
function matches(p) {
  // Keyword filters (OR: match any selected keyword in title+abstract)
  if (state.keywordActive.size) {
    const hay = [p.title, p.abstract || "", p.venue, p.authors, p.notes].join(" ").toLowerCase();
    let kwHit = false;
    for (const kw of state.keywordActive) {
      if (hay.includes(kw.toLowerCase())) { kwHit = true; break; }
    }
    if (!kwHit) return false;
  }

  // Facet filters
  for (const k of state.facetKeys) {
    if (!state.active[k].size) continue;
    const have = p.tags ? p.tags[k] : undefined;
    if (!have) return false;
    if (Array.isArray(have)) {
      let hit = false;
      for (const v of state.active[k]) {
        if (have.includes(v)) { hit = true; break; }
      }
      if (!hit) return false;
    } else {
      if (!state.active[k].has(have)) return false;
    }
  }

  // Year
  if (state.yearActive.size && !state.yearActive.has(p.year)) return false;

  // Extras
  if (state.has_code && !p.code) return false;
  if (state.has_venue && !p.venue) return false;

  // Text search (multi-term AND: every word must match somewhere)
  if (state.query) {
    const parts = [p.title, p.abstract || "", p.venue, p.authors, p.notes];
    if (p.tags) {
      for (const v of Object.values(p.tags)) {
        if (Array.isArray(v)) parts.push(...v);
        else parts.push(v);
      }
    }
    const hay = parts.join(" ").toLowerCase();
    const terms = state.query.split(/\s+/).filter(Boolean);
    for (const t of terms) {
      if (!hay.includes(t)) return false;
    }
  }
  return true;
}

function sortPapers(arr) {
  const cmp = {
    "date-desc": (a, b) => (b.date || "").localeCompare(a.date || ""),
    "date-asc": (a, b) => (a.date || "").localeCompare(b.date || ""),
    "title": (a, b) => a.title.localeCompare(b.title),
    "venue": (a, b) => (a.venue || "~").localeCompare(b.venue || "~"),
  }[state.sort];
  return [...arr].sort(cmp);
}

// ---------- render ----------
function render() {
  const filtered = state.papers.filter(matches);
  const sorted = sortPapers(filtered);

  const root = document.getElementById("results");
  const empty = document.getElementById("empty");
  root.innerHTML = "";

  if (!sorted.length) {
    empty.hidden = false;
  } else {
    empty.hidden = true;
    const frag = document.createDocumentFragment();
    for (const p of sorted) frag.appendChild(cardFor(p));
    root.appendChild(frag);
  }

  document.getElementById("result-count").innerHTML =
    `Showing <strong>${sorted.length}</strong> of ${state.papers.length} papers`;
  renderActiveTags();
  updateFacetCounts(filtered);
}

function cardFor(p) {
  const el = document.createElement("article");
  el.className = "card";

  // Title
  const title = document.createElement("h2");
  title.className = "title";
  if (p.link) {
    const a = document.createElement("a");
    a.href = p.link;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = p.title;
    title.appendChild(a);
  } else {
    title.textContent = p.title;
  }
  el.appendChild(title);

  // Meta
  const meta = document.createElement("div");
  meta.className = "meta";
  if (p.date) meta.insertAdjacentHTML("beforeend", `<span class="date">${p.date}</span>`);
  if (p.venue) meta.insertAdjacentHTML("beforeend", `<span class="venue">${esc(p.venue)}</span>`);
  if (p.authors) meta.insertAdjacentHTML("beforeend", `<span>${esc(p.authors)}</span>`);
  el.appendChild(meta);

  // Notes
  if (p.notes) {
    const n = document.createElement("div");
    n.className = "notes";
    n.textContent = p.notes;
    el.appendChild(n);
  }

  // Tag chips
  const tagRow = document.createElement("div");
  tagRow.className = "tags";
  if (p.tags) {
    for (const [facet, value] of Object.entries(p.tags)) {
      const vals = Array.isArray(value) ? value : (value ? [value] : []);
      for (const v of vals) {
        const c = document.createElement("span");
        const ci = facetColorIndex[facet] ?? 0;
        c.className = "chip";
        c.style.background = `var(--tag-${ci}-bg)`;
        c.style.color = `var(--tag-${ci}-fg)`;
        c.textContent = v;
        c.title = `Filter by ${formatLabel(facet)}: ${v}`;
        c.addEventListener("click", () => toggleActive(facet, v));
        tagRow.appendChild(c);
      }
    }
  }
  el.appendChild(tagRow);

  // Action links
  if (p.link || p.code) {
    const act = document.createElement("div");
    act.className = "actions";
    if (p.link)
      act.insertAdjacentHTML("beforeend",
        `<a href="${p.link}" target="_blank" rel="noopener">Paper</a>`);
    if (p.code)
      act.insertAdjacentHTML("beforeend",
        `<a href="${p.code}" target="_blank" rel="noopener">Code</a>`);
    el.appendChild(act);
  }
  return el;
}

function toggleActive(facet, value) {
  const s = state.active[facet];
  if (!s) return;
  if (s.has(value)) s.delete(value);
  else s.add(value);
  const escVal = CSS.escape(String(value));
  const box = document.querySelector(
    `input[data-facet="${facet}"][data-value="${escVal}"]`
  );
  if (box) box.checked = s.has(value);
  render();
}

function renderActiveTags() {
  const root = document.getElementById("active-tags");
  root.innerHTML = "";
  const chips = [];
  for (const k of state.facetKeys) {
    for (const v of state.active[k]) chips.push([k, v]);
  }
  for (const v of state.keywordActive) chips.push(["_keyword", v]);
  for (const v of state.yearActive) chips.push(["year", v]);
  if (state.has_code) chips.push(["extras", "has code"]);
  if (state.has_venue) chips.push(["extras", "has venue"]);

  for (const [k, v] of chips) {
    const c = document.createElement("span");
    c.className = "at-chip";
    c.textContent = v;
    c.addEventListener("click", () => removeActive(k, v));
    root.appendChild(c);
  }
}

function removeActive(k, v) {
  if (k === "extras") {
    if (v === "has code") {
      state.has_code = false;
      const el = document.querySelector('[data-extra="has_code"]');
      if (el) el.checked = false;
    }
    if (v === "has venue") {
      state.has_venue = false;
      const el = document.querySelector('[data-extra="has_venue"]');
      if (el) el.checked = false;
    }
  } else if (k === "_keyword") {
    state.keywordActive.delete(v);
    const escVal = CSS.escape(String(v));
    const box = document.querySelector(`input[data-facet="_keyword"][data-value="${escVal}"]`);
    if (box) box.checked = false;
  } else if (k === "year") {
    state.yearActive.delete(v);
    const box = document.querySelector(`input[data-facet="year"][data-value="${v}"]`);
    if (box) box.checked = false;
  } else {
    state.active[k].delete(v);
    const escVal = CSS.escape(String(v));
    const box = document.querySelector(`input[data-facet="${k}"][data-value="${escVal}"]`);
    if (box) box.checked = false;
  }
  render();
}

function updateFacetCounts(filtered) {
  for (const key of state.facetKeys) {
    const boxes = document.querySelectorAll(
      `.filter-group[data-facet="${key}"] input[type=checkbox]`
    );
    boxes.forEach((box) => {
      const v = box.dataset.value;
      let n = 0;
      for (const p of filtered) {
        const x = p.tags ? p.tags[key] : undefined;
        if (Array.isArray(x) ? x.includes(v) : x === v) n++;
      }
      const countEl = box.parentElement.querySelector(".count");
      if (countEl) countEl.textContent = n;
      box.parentElement.classList.toggle("is-disabled", n === 0 && !box.checked);
    });
  }

  // Year counts
  const yearBoxes = document.querySelectorAll(
    '.filter-group[data-facet="year"] input[type=checkbox]'
  );
  yearBoxes.forEach((box) => {
    const y = Number(box.dataset.value);
    const n = filtered.filter((p) => p.year === y).length;
    const countEl = box.parentElement.querySelector(".count");
    if (countEl) countEl.textContent = n;
    box.parentElement.classList.toggle("is-disabled", n === 0 && !box.checked);
  });
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

// ---------- settings panel ----------

function loadSettingsFromURL() {
  const params = new URLSearchParams(location.search);

  const kw = params.get("keywords");
  if (kw) {
    state.settings.keywords = kw.split(",").map((s) => s.trim()).filter(Boolean);
  }
  if (!state.settings.keywords.length) {
    state.settings.keywords = [...DEFAULT_KEYWORDS];
  }

  // facets param: "category:Method,Benchmark,Survey|task:Classification,Generation|..."
  const fp = params.get("facets");
  if (fp) {
    state.settings.facets = fp.split("|").map((seg) => {
      const [keyLabel, ...rest] = seg.split(":");
      const valStr = rest.join(":");
      const parts = keyLabel.split("~");
      const key = parts[0] || "";
      const label = parts[1] || formatLabel(key);
      const values = valStr ? valStr.split(",").map((s) => s.trim()).filter(Boolean) : [];
      return { key, label, values };
    }).filter((f) => f.key);
  }

  // If no facets in URL, build defaults from the data
  if (!state.settings.facets.length) {
    buildDefaultFacetSettings();
  }
}

const DEFAULT_KEYWORDS = ["agent", "neuro-symbolic"];

const DEFAULT_FACETS = [
  { key: "category", label: "Category", values: ["Method", "Benchmark", "Survey"] },
  { key: "task", label: "Task", values: ["Classification", "Generation", "Detection"] },
  { key: "modality", label: "Modality", values: ["Text", "Image", "Video", "Audio", "Multimodal"] },
];

function buildDefaultFacetSettings() {
  // Start with config defaults, then merge any extra keys discovered from data
  const used = new Set(DEFAULT_FACETS.map((f) => f.key));
  const fromData = state.facetKeys
    .filter((k) => !used.has(k))
    .map((key) => {
      const values = [...tallyFacet(key).keys()].sort();
      return { key, label: formatLabel(key), values };
    })
    .filter((f) => f.values.length > 0);
  state.settings.facets = [...cloneFacets(DEFAULT_FACETS), ...fromData];
}

function settingsToURL() {
  const params = new URLSearchParams();
  if (state.settings.keywords.length) {
    params.set("keywords", state.settings.keywords.join(","));
  }
  if (state.settings.facets.length) {
    const segs = state.settings.facets.map((f) =>
      `${f.key}~${f.label}:${f.values.join(",")}`
    );
    params.set("facets", segs.join("|"));
  }
  const qs = params.toString();
  const newURL = location.pathname + (qs ? "?" + qs : "");
  history.replaceState(null, "", newURL);
}

function bindSettings() {
  const btn = document.getElementById("settings-btn");
  const overlay = document.getElementById("settings-overlay");
  const closeBtn = document.getElementById("settings-close");

  btn.addEventListener("click", openSettings);
  overlay.addEventListener("click", closeSettings);
  closeBtn.addEventListener("click", closeSettings);

  document.getElementById("sp-apply").addEventListener("click", applySettings);
  document.getElementById("sp-reset").addEventListener("click", resetSettings);
  document.getElementById("sp-copy-config").addEventListener("click", copyConfig);

  // Keyword input: add on Enter (skip during IME composition)
  const kwInput = document.getElementById("kw-input");
  let composing = false;
  kwInput.addEventListener("compositionstart", () => { composing = true; });
  kwInput.addEventListener("compositionend", () => { composing = false; });
  kwInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing && !composing) {
      e.preventDefault();
      const val = kwInput.value.trim().replace(/\s+/g, " ");
      if (val && !settingsTemp.keywords.includes(val)) {
        settingsTemp.keywords.push(val);
        renderKeywordTags();
      }
      kwInput.value = "";
    }
  });

  // Add dimension button
  document.getElementById("add-facet-btn").addEventListener("click", () => {
    const idx = settingsTemp.facets.length;
    settingsTemp.facets.push({ key: `dim${idx + 1}`, label: `Dimension ${idx + 1}`, values: [] });
    renderFacetEditor();
  });
}

let settingsTemp = { keywords: [], facets: [] };

function cloneFacets(facets) {
  return facets.map((f) => ({ key: f.key, label: f.label, values: [...f.values] }));
}

function openSettings() {
  settingsTemp = {
    keywords: [...state.settings.keywords],
    facets: cloneFacets(state.settings.facets),
  };

  document.getElementById("settings-overlay").hidden = false;
  document.getElementById("settings-panel").hidden = false;

  renderKeywordTags();
  renderFacetEditor();
}

function closeSettings() {
  document.getElementById("settings-overlay").hidden = true;
  document.getElementById("settings-panel").hidden = true;
}

function renderKeywordTags() {
  const container = document.getElementById("kw-tags");
  container.innerHTML = "";
  settingsTemp.keywords.forEach((kw, i) => {
    const tag = document.createElement("span");
    tag.className = "fe-val";
    const ci = (i + 4) % 8;
    tag.style.background = `var(--tag-${ci}-bg)`;
    tag.style.color = `var(--tag-${ci}-fg)`;

    const text = document.createElement("span");
    text.textContent = kw;
    tag.appendChild(text);

    const btn = document.createElement("span");
    btn.className = "fe-val-remove";
    btn.textContent = "\u00d7";
    btn.addEventListener("click", () => {
      settingsTemp.keywords = settingsTemp.keywords.filter((k) => k !== kw);
      renderKeywordTags();
    });
    tag.appendChild(btn);

    container.appendChild(tag);
  });
}

function renderFacetEditor() {
  const container = document.getElementById("facet-editor");
  container.innerHTML = "";

  settingsTemp.facets.forEach((facet, fi) => {
    const ci = fi % 8;
    const card = document.createElement("div");
    card.className = "fe-card";

    // Header: key input + label input + remove button
    const head = document.createElement("div");
    head.className = "fe-head";

    const headLeft = document.createElement("div");
    headLeft.className = "fe-head-left";

    const labelIn = document.createElement("input");
    labelIn.className = "fe-label-input";
    labelIn.value = facet.label;
    labelIn.placeholder = "Dimension name";
    labelIn.addEventListener("input", () => {
      facet.label = labelIn.value.trim();
      facet.key = facet.label.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
    });

    headLeft.appendChild(labelIn);

    const removeBtn = document.createElement("button");
    removeBtn.className = "fe-remove-dim";
    removeBtn.textContent = "\u00d7";
    removeBtn.title = "Remove dimension";
    removeBtn.addEventListener("click", () => {
      settingsTemp.facets.splice(fi, 1);
      renderFacetEditor();
    });

    head.appendChild(headLeft);
    head.appendChild(removeBtn);
    card.appendChild(head);

    // Body: value tags + input
    const body = document.createElement("div");
    body.className = "fe-body";

    const valContainer = document.createElement("div");
    valContainer.className = "fe-values";

    function renderValues() {
      valContainer.innerHTML = "";
      facet.values.forEach((v, vi) => {
        const chip = document.createElement("span");
        chip.className = "fe-val";
        chip.style.background = `var(--tag-${ci}-bg)`;
        chip.style.color = `var(--tag-${ci}-fg)`;

        const t = document.createElement("span");
        t.textContent = v;
        chip.appendChild(t);

        const x = document.createElement("span");
        x.className = "fe-val-remove";
        x.textContent = "\u00d7";
        x.addEventListener("click", () => {
          facet.values.splice(vi, 1);
          renderValues();
        });
        chip.appendChild(x);

        valContainer.appendChild(chip);
      });
    }
    renderValues();
    body.appendChild(valContainer);

    const valInput = document.createElement("input");
    valInput.className = "fe-val-input";
    valInput.placeholder = "Add value, press Enter\u2026";

    let valComposing = false;
    valInput.addEventListener("compositionstart", () => { valComposing = true; });
    valInput.addEventListener("compositionend", () => { valComposing = false; });
    valInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing && !valComposing) {
        e.preventDefault();
        const v = valInput.value.trim();
        if (v && !facet.values.includes(v)) {
          facet.values.push(v);
          renderValues();
        }
        valInput.value = "";
      }
    });

    body.appendChild(valInput);
    card.appendChild(body);
    container.appendChild(card);
  });
}

function applySettings() {
  state.settings.keywords = [...settingsTemp.keywords];
  state.settings.facets = cloneFacets(settingsTemp.facets);

  settingsToURL();
  buildSidebar();
  render();
  closeSettings();
}

function resetSettings() {
  settingsTemp = {
    keywords: [],
    facets: cloneFacets(state.settings.facets),
  };
  buildDefaultFacetSettings();
  settingsTemp.facets = cloneFacets(state.settings.facets);
  renderKeywordTags();
  renderFacetEditor();
}

function copyConfig() {
  const lines = ["keywords:"];
  if (settingsTemp.keywords.length) {
    for (const kw of settingsTemp.keywords) lines.push(`  - "${kw}"`);
  } else {
    lines.push('  - "keyword1"');
  }

  lines.push("");
  lines.push("facets:");
  for (const f of settingsTemp.facets) {
    lines.push(`  - key: "${f.key}"`);
    lines.push(`    label: "${f.label}"`);
    lines.push(`    values: [${f.values.map((v) => `"${v}"`).join(", ")}]`);
  }

  const text = lines.join("\n");
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("sp-copy-config");
    const orig = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {
    prompt("Copy this config.yaml snippet:", text);
  });
}
