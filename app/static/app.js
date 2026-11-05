// Mangrove Decision Support System: map dashboard.
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const VERDICT = {
  suitable: "Suitable for planting",
  partly_suitable: "Partly suitable",
  not_suitable: "Not suitable",
  protect: "Protect existing mangrove",
  uncertain: "Not enough data",
};
const LAYER_NAMES = {
  dem: "elevation", coast: "coastline", rivers: "rivers", roads: "roads", gmw: "mangrove map",
  fishponds: "fishponds", builtup: "built-up areas", clay: "soil", ndvi: "Sentinel-2 greenness",
  ndvi_change: "Sentinel-2 change", observations: "species records",
};
const PART_NAMES = {
  habitat_evidence: "Habitat evidence", zone_fit: "Zone fit", need: "Need", access: "Access",
  suitable_share: "Suitable share",
};

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}
const postJSON = (path, data) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

// ------------------------------------------------------------------ tabs
document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
  if (name === "sites") loadSites();
  if (name === "corrections") loadCorrections();
}

// ------------------------------------------------------------------ map
const map = L.map("map", { zoomControl: true }).setView([10.85, 122.55], 10);
const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: "© OpenStreetMap contributors",
}).addTo(map);
const sat = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 19, attribution: "Imagery © Esri",
});

const gmwLayer = L.geoJSON(null, { style: { color: "#15803d", weight: 1, fillColor: "#22c55e", fillOpacity: 0.35 } });
const pondLayer = L.geoJSON(null, { style: { color: "#0e7490", weight: 1, fillColor: "#67e8f9", fillOpacity: 0.2, dashArray: "3" } });
const sitesLayer = L.layerGroup().addTo(map);
const samplesLayer = L.layerGroup().addTo(map);
const drawn = new L.FeatureGroup().addTo(map);
gmwLayer.addTo(map);

L.control.layers(
  { "Street map": osm, "Satellite": sat },
  { "Mangroves (GMW 2020)": gmwLayer, "Fishponds (OSM)": pondLayer, "Saved sites": sitesLayer, "Area sample points": samplesLayer },
  { collapsed: false }
).addTo(map);

map.addControl(new L.Control.Draw({
  draw: { polygon: { showArea: true, shapeOptions: { color: "#b45309" } }, rectangle: { shapeOptions: { color: "#b45309" } },
          polyline: false, circle: false, marker: false, circlemarker: false },
  edit: { featureGroup: drawn, edit: false, remove: true },
}));

let marker = null;
let current = null; // { kind: "point"|"area", lat, lon, coordinates?, result }

map.on("click", (e) => assessPoint(e.latlng.lat, e.latlng.lng));
map.on(L.Draw.Event.CREATED, (e) => {
  drawn.clearLayers();
  drawn.addLayer(e.layer);
  const ring = e.layer.getLatLngs()[0].map((p) => [p.lng, p.lat]);
  ring.push(ring[0]);
  assessArea(ring);
});

// Load vector overlays for the current view.
async function refreshOverlays() {
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(5)).join(",");
  for (const [name, layer] of [["gmw", gmwLayer], ["fishponds", pondLayer]]) {
    if (!map.hasLayer(layer)) continue;
    try {
      const fc = await api(`/api/layers/${name}?bbox=${bbox}`);
      layer.clearLayers();
      if (!fc.too_large) layer.addData(fc);
    } catch (_) { /* layer missing: ignore */ }
  }
}
map.on("moveend overlayadd", refreshOverlays);

// ------------------------------------------------------------------ assessment
async function assessPoint(lat, lon) {
  showTab("assess");
  samplesLayer.clearLayers();
  if (marker) marker.setLatLng([lat, lon]); else marker = L.marker([lat, lon]).addTo(map);
  $("#result").innerHTML = `<p class="loading">Measuring site factors…</p>`;
  try {
    const r = await api(`/api/assess?lat=${lat}&lon=${lon}`);
    current = { kind: "point", lat, lon, result: r };
    renderResult(r, `${lat.toFixed(5)}, ${lon.toFixed(5)}`);
  } catch (err) {
    $("#result").innerHTML = `<div class="card">${esc(err.message)}</div>`;
  }
}

async function assessArea(ring) {
  showTab("assess");
  if (marker) { map.removeLayer(marker); marker = null; }
  samplesLayer.clearLayers();
  $("#result").innerHTML = `<p class="loading">Assessing sample points inside the area…</p>`;
  try {
    const r = await postJSON("/api/assess-area", { coordinates: ring });
    const c = L.polygon(ring.map(([x, y]) => [y, x])).getBounds().getCenter();
    current = { kind: "area", lat: c.lat, lon: c.lng, coordinates: ring, result: r };
    const colors = { suitable: "#15803d", not_suitable: "#b91c1c", protect: "#1d4ed8", uncertain: "#6b7280" };
    r.points.forEach((p) => L.circleMarker([p.lat, p.lon], {
      radius: 4, weight: 1, color: "#fff", fillColor: colors[p.verdict] || "#6b7280", fillOpacity: 0.9,
    }).bindTooltip(VERDICT[p.verdict] || p.verdict).addTo(samplesLayer));
    renderResult(r, `Drawn area · ${r.area_ha} ha · ${r.sample_points} sample points`);
  } catch (err) {
    $("#result").innerHTML = `<div class="card">${esc(err.message)}</div>`;
  }
}

function renderResult(r, where) {
  const reasons = (r.reasons || []).map((x) => `<li>${esc(x)}</li>`).join("");
  const cautions = (r.cautions || []).map((x) => `<div class="caution">${esc(x)}</div>`).join("");
  const species = (r.species || []).map((s) => `
    <div class="sp">
      <div class="sp-top"><span class="sp-name">${esc(s.name)} <span class="sp-local">· ${esc(s.local)}</span></span><b>${s.score}</b></div>
      <div class="bar"><i style="width:${s.score}%"></i></div>
      <div class="sp-why">${esc((s.reasons || []).join(" "))}</div>
    </div>`).join("");
  const pr = r.priority;
  const parts = pr ? Object.entries(pr.parts).map(([k, v]) =>
    `<tr><td>${esc(PART_NAMES[k] || k)}</td><td>${v.points}</td><td>${esc(v.why)}</td></tr>`).join("") : "";
  const missing = (r.missing_layers || []).map((m) => LAYER_NAMES[m] || m);

  $("#result").innerHTML = `
    <div class="card">
      <span class="verdict v-${esc(r.verdict)}">${esc(VERDICT[r.verdict] || r.verdict)}</span>
      <div class="coords">${esc(where)}</div>
      ${r.zone_label ? `<h3>Zone</h3><div>${esc(r.zone_label)}</div>` : r.zone ? `<h3>Main zone</h3><div>${esc(r.zone)}</div>` : ""}
      <h3>Why</h3><ul class="reasons">${reasons}</ul>
      ${cautions ? `<h3>Before planting</h3>${cautions}` : ""}
    </div>
    ${species ? `<div class="card"><h2>Recommended species</h2>${species}
      <p class="meta">Scores combine zone fit, soil and species already growing nearby. Draft rules from published zonation studies; confirm in the field.</p></div>` : ""}
    ${pr ? `<div class="card"><h2>Planting priority</h2>
      <div class="prio"><b>${pr.score}</b><span>/ 100 · ${esc(pr.level)}</span></div>
      <table class="parts">${parts}</table></div>` : ""}
    <div class="card">
      <div class="meta">Confidence: <b>${esc(r.confidence)}</b>${missing.length ? ` · Missing data: ${esc(missing.join(", "))}` : ""}</div>
      <div class="row">
        <button id="save-site">Save as candidate site</button>
        <button id="open-correct" class="ghost">Correct this result</button>
      </div>
    </div>`;
  $("#save-site").onclick = saveSite;
  $("#open-correct").onclick = () => openCorrection();
}

// ------------------------------------------------------------------ sites
async function saveSite() {
  if (!current) return;
  const name = prompt("Name for this candidate site:", current.kind === "area" ? "Drawn area" : "Candidate site");
  if (!name) return;
  const body = current.kind === "area"
    ? { name, coordinates: current.coordinates }
    : { name, lat: current.lat, lon: current.lon };
  try {
    await postJSON("/api/sites", body);
    showTab("sites");
  } catch (err) { alert(err.message); }
}

async function loadSites() {
  const el = $("#sites");
  el.innerHTML = `<p class="loading">Loading…</p>`;
  const sites = await api("/api/sites");
  sitesLayer.clearLayers();
  if (!sites.length) { el.innerHTML = `<p class="empty">No saved sites yet.</p>`; return; }
  let rank = 0;
  el.innerHTML = sites.map((s) => {
    const r = s.result || {};
    const top = (r.species || []).slice(0, 2).map((x) => x.name).join(", ");
    const isRanked = s.verdict === "suitable" || s.verdict === "partly_suitable";
    return `<div class="site" data-id="${s.id}">
      <div class="rank">${isRanked ? ++rank : "–"}</div>
      <div class="grow">
        <b>${esc(s.name)}</b><br>
        <span class="verdict v-${esc(s.verdict)}" style="font-size:11px;padding:2px 6px">${esc(VERDICT[s.verdict] || s.verdict)}</span>
        ${s.priority != null ? ` <span class="meta">Priority ${s.priority} (${esc(r.priority?.level || "")})</span>` : ""}
        ${top ? `<div class="meta"><i>${esc(top)}</i></div>` : ""}
      </div>
      <button class="danger" data-del="${s.id}">Delete</button>
    </div>`;
  }).join("");

  sites.forEach((s) => {
    const shape = s.polygon
      ? L.polygon(s.polygon.map(([x, y]) => [y, x]), { color: "#1d4ed8", weight: 2, fillOpacity: 0.1 })
      : L.circleMarker([s.lat, s.lon], { radius: 7, color: "#1d4ed8", fillOpacity: 0.6 });
    shape.bindTooltip(s.name).addTo(sitesLayer);
  });
  el.querySelectorAll(".site").forEach((row) => row.addEventListener("click", (e) => {
    const s = sites.find((x) => x.id == row.dataset.id);
    if (e.target.dataset.del) return;
    map.setView([s.lat, s.lon], 15);
    current = { kind: s.polygon ? "area" : "point", lat: s.lat, lon: s.lon, coordinates: s.polygon, result: s.result, site_id: s.id };
    showTab("assess");
    renderResult(s.result, s.name);
  }));
  el.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm("Delete this site?")) return;
    await api(`/api/sites/${b.dataset.del}`, { method: "DELETE" });
    loadSites();
  }));
}

// ------------------------------------------------------------------ corrections
const dlg = $("#correct-dialog");
function openCorrection() {
  if (!current) return;
  $("#correct-form").reset();
  dlg.showModal();
}
$("#correct-cancel").onclick = () => dlg.close();
$("#correct-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = Object.fromEntries(new FormData(e.target));
  const r = current.result;
  try {
    await postJSON("/api/corrections", {
      lat: current.lat, lon: current.lon, site_id: current.site_id || null,
      original_verdict: r.verdict,
      original_species: (r.species || []).map((s) => s.name).join(", "),
      corrected_verdict: fd.corrected_verdict || null,
      corrected_species: fd.corrected_species || null,
      notes: fd.notes || null, expert: fd.expert,
    });
    dlg.close();
    showTab("corrections");
  } catch (err) { alert(err.message); }
});

async function loadCorrections() {
  const el = $("#corrections");
  const rows = await api("/api/corrections");
  if (!rows.length) { el.innerHTML = `<p class="empty">No corrections yet.</p>`; return; }
  el.innerHTML = rows.map((c) => `<div class="card">
    <div class="meta">${esc(c.created_at.slice(0, 10))} · ${esc(c.expert)} · ${c.lat.toFixed(4)}, ${c.lon.toFixed(4)}</div>
    <div><b>System:</b> ${esc(VERDICT[c.original_verdict] || c.original_verdict || "–")}${c.original_species ? ` · <i>${esc(c.original_species)}</i>` : ""}</div>
    <div><b>Expert:</b> ${esc(VERDICT[c.corrected_verdict] || "(verdict unchanged)")}${c.corrected_species ? ` · <i>${esc(c.corrected_species)}</i>` : ""}</div>
    ${c.notes ? `<div class="meta">${esc(c.notes)}</div>` : ""}
  </div>`).join("");
}

// ------------------------------------------------------------------ Module 1: canopy
$("#canopy-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const el = $("#canopy-result");
  el.innerHTML = `<p class="loading">Measuring canopy…</p>`;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("/api/canopy", { method: "POST", body: fd });
    el.innerHTML = `<div class="card">
      <div class="big">${r.canopy_cover_pct}%</div>
      <div>canopy coverage · <b>${esc(r.density_class)}</b></div>
      <img class="canopy-img" alt="Vegetation highlighted in green" src="data:image/jpeg;base64,${r.overlay_jpeg_base64}">
      <p class="meta">${esc(r.note)}</p>
    </div>`;
  } catch (err) {
    el.innerHTML = `<div class="card">${esc(err.message)}</div>`;
  }
});

// ------------------------------------------------------------------ status
(async function init() {
  try {
    const s = await api("/api/status");
    map.setView(s.center, 10);
    const have = Object.values(s.layers).filter(Boolean).length;
    const total = Object.keys(s.layers).length;
    $("#status-pill").textContent = `Data layers loaded: ${have} of ${total}`;
    $("#status-pill").title = Object.entries(s.layers).map(([k, v]) => `${v ? "✓" : "✗"} ${LAYER_NAMES[k] || k}`).join("\n");
  } catch (_) {
    $("#status-pill").textContent = "Backend not reachable";
  }
  refreshOverlays();
})();
