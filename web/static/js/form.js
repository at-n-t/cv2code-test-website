/* ============================================================
   CV2CC — Form logic, step navigation, live compliance check
   ============================================================ */

"use strict";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RISK_DESC = {
  "I":   "Low hazard — minor storage, agriculture",
  "II":  "Normal hazard — most buildings",
  "III": "Substantial hazard — schools, assembly >300",
  "IV":  "Essential facilities — hospitals, fire stations",
};

const CONSTRUCTION_DESC = {
  "I-A":   "Non-combustible, fully fire-resistive",
  "I-B":   "Non-combustible, fire-resistive",
  "II-A":  "Non-combustible, protected",
  "II-B":  "Non-combustible, unprotected",
  "III-A": "Exterior masonry, interior wood, protected",
  "III-B": "Exterior masonry, interior wood, unprotected",
  "IV":    "Heavy timber",
  "V-A":   "Combustible, protected",
  "V-B":   "Combustible, unprotected (lowest)",
};

const TOOLTIP_CONTENT = {
  risk: `<strong>IBC Table 1604.5 — Risk Categories</strong><br>
    <b>I</b> — Minor storage, agriculture<br>
    <b>II</b> — Most buildings (default)<br>
    <b>III</b> — Schools, assembly (&gt;300 occ.), healthcare<br>
    <b>IV</b> — Hospitals, fire stations, emergency ops`,
  construction: `<strong>IBC Chapter 6 — Construction Types</strong><br>
    <b>I-A/I-B</b> — Steel/concrete, most fire resistance<br>
    <b>II-A/II-B</b> — Non-combustible frame<br>
    <b>III-A/III-B</b> — Masonry exterior, wood interior<br>
    <b>IV</b> — Heavy timber<br>
    <b>V-A/V-B</b> — Wood frame (most common residential)`,
  occupancy: `<strong>IBC Chapter 3 — Occupancy Classifications</strong><br>
    <b>A</b> — Assembly &nbsp;|&nbsp; <b>B</b> — Business<br>
    <b>E</b> — Educational &nbsp;|&nbsp; <b>F</b> — Factory<br>
    <b>H</b> — High Hazard &nbsp;|&nbsp; <b>I</b> — Institutional<br>
    <b>M</b> — Mercantile &nbsp;|&nbsp; <b>R</b> — Residential<br>
    <b>S</b> — Storage &nbsp;|&nbsp; <b>U</b> — Utility`,
};

// ---------------------------------------------------------------------------
// Step navigation
// ---------------------------------------------------------------------------

let currentStep = 1;
const TOTAL_STEPS = 6;

function goStep(n) {
  const current = document.getElementById(`step-${currentStep}`);
  const next    = document.getElementById(`step-${n}`);
  if (!next) return;

  current.classList.remove("active");
  next.classList.add("active");

  // Update step bar
  document.querySelectorAll(".step-item").forEach(btn => {
    const s = parseInt(btn.dataset.step);
    btn.classList.remove("active", "done");
    if (s === n)         btn.classList.add("active");
    else if (s < n)      btn.classList.add("done");
  });

  currentStep = n;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Step bar click
document.querySelectorAll(".step-item").forEach(btn => {
  btn.addEventListener("click", () => goStep(parseInt(btn.dataset.step)));
});

// ---------------------------------------------------------------------------
// State auto-fill
// ---------------------------------------------------------------------------

document.getElementById("state").addEventListener("change", async function () {
  const st = this.value;
  if (!st) return;
  const res  = await fetch(`/api/state-codes/${st}`);
  const data = await res.json();
  if (data.ibc) document.getElementById("ibc_edition").value = data.ibc;
  if (data.irc) document.getElementById("irc_edition").value = data.irc;

  const noteEl = document.getElementById("state-note");
  if (data.notes) {
    noteEl.textContent = data.notes;
    noteEl.style.display = "block";
  } else {
    noteEl.style.display = "none";
  }
});

// ---------------------------------------------------------------------------
// Risk / Construction type live hints
// ---------------------------------------------------------------------------

function updateRiskHint() {
  const v = document.getElementById("risk_category").value;
  document.getElementById("risk-hint").textContent = RISK_DESC[v] || "";
  document.getElementById("info-risk-val").textContent  = v;
  document.getElementById("info-risk-desc").textContent = RISK_DESC[v] || "";
}

function updateConstructionHint() {
  const v = document.getElementById("construction_type").value;
  document.getElementById("construction-hint").textContent = CONSTRUCTION_DESC[v] || "";
  document.getElementById("info-const-val").textContent  = v;
  document.getElementById("info-const-desc").textContent = CONSTRUCTION_DESC[v] || "";
}

document.getElementById("risk_category").addEventListener("change", updateRiskHint);
document.getElementById("construction_type").addEventListener("change", updateConstructionHint);
updateRiskHint();
updateConstructionHint();

// ---------------------------------------------------------------------------
// Occupancy chip tracking → sidebar + mixed-occupancy row
// ---------------------------------------------------------------------------

function getSelectedOccupancies() {
  return Array.from(document.querySelectorAll('input[name="occupancy_groups"]:checked'))
              .map(cb => cb.value);
}

document.querySelectorAll('input[name="occupancy_groups"]').forEach(cb => {
  cb.addEventListener("change", () => {
    const selected = getSelectedOccupancies();
    // Update sidebar
    const container = document.getElementById("info-occ-val");
    if (selected.length === 0) {
      container.innerHTML = "—";
    } else {
      container.innerHTML = selected.map(o => `<span class="info-chip">${o}</span>`).join("");
    }
    // Show mixed occupancy row if >1 selected
    const row = document.getElementById("mixed-occ-row");
    row.style.display = selected.length > 1 ? "block" : "none";
  });
});

// ---------------------------------------------------------------------------
// Toggle switches
// ---------------------------------------------------------------------------

function bindToggle(checkboxId, labelId, onText, offText, showIds = [], hideIds = []) {
  const cb    = document.getElementById(checkboxId);
  const label = document.getElementById(labelId);
  cb.addEventListener("change", () => {
    label.textContent = cb.checked ? onText : offText;
    showIds.forEach(id => {
      document.getElementById(id).style.display = cb.checked ? "block" : "none";
    });
  });
}

bindToggle("sprinkler_system",  "sprinkler-label",  "Yes", "No", ["sprinkler-standard-field"]);
bindToggle("fire_alarm_system", "alarm-label",      "Yes", "No", ["alarm-standard-field"]);
bindToggle("ada_compliant",     "ada-label",        "Yes", "No");
bindToggle("accessible_route",  "route-label",      "Yes", "No");

// ---------------------------------------------------------------------------
// Parking requirement hint
// ---------------------------------------------------------------------------

function parkingHint() {
  const total = parseInt(document.getElementById("total_parking_spaces").value) || 0;
  let req = 0;
  if (total <= 25)   req = 1;
  else if (total <= 50)  req = 2;
  else if (total <= 75)  req = 3;
  else if (total <= 100) req = 4;
  else if (total <= 150) req = 5;
  else if (total <= 200) req = 6;
  else if (total <= 300) req = 7;
  else if (total <= 400) req = 8;
  else if (total <= 500) req = 9;
  else if (total <= 1000) req = Math.ceil(total * 0.02);
  else req = 20 + Math.ceil((total - 1000) / 100);

  const hint = document.getElementById("parking-req-hint");
  if (total > 0) {
    hint.textContent = `Minimum ${req} accessible space(s) required (ADA / IBC 1106.1)`;
  } else {
    hint.textContent = "";
  }
}
document.getElementById("total_parking_spaces").addEventListener("input", parkingHint);

// ---------------------------------------------------------------------------
// Room schedule
// ---------------------------------------------------------------------------

let roomIndex = 0;

function addRoomRow(data = {}) {
  const idx = roomIndex++;
  const tbody = document.getElementById("room-tbody");
  const tr = document.createElement("tr");
  tr.dataset.idx = idx;

  const ogOptions = OCCUPANCY_GROUPS.map(og =>
    `<option value="${og}" ${(data.occupancy_group === og) ? "selected" : ""}>${og}</option>`
  ).join("");

  tr.innerHTML = `
    <td><input type="text" placeholder="Room name"
               value="${escHtml(data.name || '')}"
               onchange="recalcRoom(${idx})" /></td>
    <td>
      <select onchange="fetchLoadFactor(${idx})">
        ${ogOptions}
      </select>
    </td>
    <td><input type="number" min="0" step="1" placeholder="0"
               value="${data.floor_area_sqft || ''}"
               style="width:90px" onchange="recalcRoom(${idx})" /></td>
    <td><input type="number" min="0" step="0.1" placeholder="auto"
               value="${data.occupant_load_factor || ''}"
               style="width:80px" onchange="recalcRoom(${idx})" /></td>
    <td class="occ-load-cell" id="load-cell-${idx}">—</td>
    <td><button class="btn-del-row" onclick="removeRoomRow(this)" title="Remove">&#215;</button></td>
  `;
  tbody.appendChild(tr);

  // Trigger load factor lookup for the default occupancy
  fetchLoadFactor(idx);
  return tr;
}

async function fetchLoadFactor(idx) {
  const tr  = document.querySelector(`tr[data-idx="${idx}"]`);
  if (!tr) return;
  const og  = tr.querySelectorAll("td")[1].querySelector("select").value;
  const lfInput = tr.querySelectorAll("td")[3].querySelector("input");
  // Only auto-fill if empty
  if (lfInput.value !== "") { recalcRoom(idx); return; }

  const res  = await fetch(`/api/occupant-load-factor/${og}`);
  const data = await res.json();
  if (data.factor > 0) {
    lfInput.value       = data.factor;
    lfInput.title       = data.note || "";
    lfInput.placeholder = data.factor;
  } else {
    lfInput.value       = "";
    lfInput.placeholder = "N/A";
  }
  recalcRoom(idx);
}

function recalcRoom(idx) {
  const tr   = document.querySelector(`tr[data-idx="${idx}"]`);
  if (!tr) return;
  const tds  = tr.querySelectorAll("td");
  const area = parseFloat(tds[2].querySelector("input").value) || 0;
  const lf   = parseFloat(tds[3].querySelector("input").value) || 0;
  const cell = document.getElementById(`load-cell-${idx}`);
  if (area > 0 && lf > 0) {
    cell.textContent = Math.ceil(area / lf).toLocaleString();
  } else {
    cell.textContent = "—";
  }
  updateTotals();
}

function removeRoomRow(btn) {
  btn.closest("tr").remove();
  updateTotals();
}

function updateTotals() {
  let totalArea = 0, totalLoad = 0, hasLoad = false;
  document.querySelectorAll("#room-tbody tr").forEach(tr => {
    const tds = tr.querySelectorAll("td");
    totalArea += parseFloat(tds[2].querySelector("input").value) || 0;
    const loadText = document.getElementById(`load-cell-${tr.dataset.idx}`)?.textContent;
    if (loadText && loadText !== "—") {
      totalLoad += parseInt(loadText.replace(/,/g, "")) || 0;
      hasLoad = true;
    }
  });
  document.getElementById("total-area").textContent =
    totalArea > 0 ? totalArea.toLocaleString() + " sf" : "—";
  document.getElementById("total-occ-load").textContent =
    hasLoad ? totalLoad.toLocaleString() : "—";
  document.getElementById("info-load-val").textContent =
    hasLoad ? totalLoad.toLocaleString() : "—";
}

document.getElementById("btn-add-room").addEventListener("click", () => addRoomRow());

// ---------------------------------------------------------------------------
// Build JSON payload from form
// ---------------------------------------------------------------------------

function buildPayload() {
  const additionalRaw = document.getElementById("additional_codes").value;
  const additionalCodes = additionalRaw
    ? additionalRaw.split(",").map(s => s.trim()).filter(Boolean)
    : [];

  const rooms = [];
  document.querySelectorAll("#room-tbody tr").forEach(tr => {
    const tds = tr.querySelectorAll("td");
    const name  = tds[0].querySelector("input").value.trim();
    const og    = tds[1].querySelector("select").value;
    const area  = parseFloat(tds[2].querySelector("input").value) || 0;
    const lf    = parseFloat(tds[3].querySelector("input").value) || 0;
    if (name || area > 0) {
      rooms.push({ name, occupancy_group: og, floor_area_sqft: area, occupant_load_factor: lf });
    }
  });

  const selectedOcc = getSelectedOccupancies();

  return {
    project_name:     document.getElementById("project_name").value.trim(),
    project_number:   document.getElementById("project_number").value.trim(),
    permit_number:    document.getElementById("permit_number").value.trim(),
    date_prepared:    document.getElementById("date_prepared").value,
    prepared_by:      document.getElementById("prepared_by").value.trim(),
    architect_license:document.getElementById("architect_license").value.trim(),
    engineer_license: document.getElementById("engineer_license").value.trim(),
    site_address:     document.getElementById("site_address").value.trim(),
    parcel_number:    document.getElementById("parcel_number").value.trim(),
    jurisdiction: {
      country:          document.getElementById("country").value.trim(),
      state:            document.getElementById("state").value,
      county:           document.getElementById("county").value.trim(),
      city:             document.getElementById("city").value.trim(),
      ibc_edition:      document.getElementById("ibc_edition").value.trim(),
      irc_edition:      document.getElementById("irc_edition").value.trim(),
      nfpa_edition:     document.getElementById("nfpa_edition").value.trim(),
      local_amendments: document.getElementById("local_amendments").value.trim(),
    },
    zoning_district:        document.getElementById("zoning_district").value,
    risk_category:          document.getElementById("risk_category").value,
    construction_type:      document.getElementById("construction_type").value,
    occupancy_groups:       selectedOcc,
    mixed_occupancy:        selectedOcc.length > 1,
    mixed_occupancy_method: document.getElementById("mixed_occupancy_method").value,
    stories_above_grade:    parseInt(document.getElementById("stories_above_grade").value) || 1,
    stories_below_grade:    parseInt(document.getElementById("stories_below_grade").value) || 0,
    building_height_ft:     parseFloat(document.getElementById("building_height_ft").value) || 0,
    total_floor_area_sqft:  parseFloat(document.getElementById("total_floor_area_sqft").value) || 0,
    footprint_sqft:         parseFloat(document.getElementById("footprint_sqft").value) || 0,
    rooms,
    sprinkler_system:       document.getElementById("sprinkler_system").checked,
    sprinkler_standard:     document.getElementById("sprinkler_standard").value,
    fire_alarm_system:      document.getElementById("fire_alarm_system").checked,
    fire_alarm_standard:    document.getElementById("fire_alarm_standard").value,
    ada_compliant:          document.getElementById("ada_compliant").checked,
    accessible_route:       document.getElementById("accessible_route").checked,
    total_parking_spaces:   parseInt(document.getElementById("total_parking_spaces").value) || 0,
    accessible_parking_spaces: parseInt(document.getElementById("accessible_parking_spaces").value) || 0,
    energy_code:            document.getElementById("energy_code").value.trim(),
    climate_zone:           document.getElementById("climate_zone").value.trim(),
    osha_applicable:        false,
    ifc_edition:            document.getElementById("ifc_edition").value.trim(),
    additional_codes:       additionalCodes,
    special_conditions:     document.getElementById("special_conditions").value.trim(),
    variances_requested:    document.getElementById("variances_requested").value.trim(),
  };
}

// ---------------------------------------------------------------------------
// Compliance check
// ---------------------------------------------------------------------------

async function runCheck() {
  goStep(6);

  const loadingEl  = document.getElementById("findings-loading");
  const summaryEl  = document.getElementById("findings-summary");
  const emptyEl    = document.getElementById("findings-empty");
  const genBlock   = document.getElementById("generate-block");
  const secViol    = document.getElementById("section-violations");
  const secWarn    = document.getElementById("section-warnings");
  const secPass    = document.getElementById("section-passes");

  [loadingEl].forEach(el => el.style.display = "flex");
  [summaryEl, emptyEl, genBlock, secViol, secWarn, secPass].forEach(el => el.style.display = "none");

  try {
    const res  = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    const data = await res.json();
    loadingEl.style.display = "none";

    if (!data.ok) {
      emptyEl.textContent = "Error: " + data.error;
      emptyEl.style.display = "block";
      return;
    }

    const violations = data.findings.filter(f => f.level === "VIOLATION");
    const warnings   = data.findings.filter(f => f.level === "WARNING");
    const passes     = data.findings.filter(f => f.level === "PASS");

    // Badges
    document.getElementById("badge-pass").textContent = `${passes.length} PASS`;
    document.getElementById("badge-warn").textContent = `${warnings.length} WARNINGS`;
    document.getElementById("badge-fail").textContent = `${violations.length} VIOLATIONS`;
    document.getElementById("badge-load").textContent = `Load: ${(data.total_occupant_load || 0).toLocaleString()}`;
    summaryEl.style.display = "flex";

    // Populate lists
    renderFindings("list-violations", violations);
    renderFindings("list-warnings",   warnings);
    renderFindings("list-passes",     passes);

    secViol.style.display = violations.length ? "block" : "none";
    secWarn.style.display = warnings.length   ? "block" : "none";
    secPass.style.display = passes.length     ? "block" : "none";

    if (data.findings.length === 0) emptyEl.style.display = "block";

    genBlock.style.display = "block";

  } catch (err) {
    loadingEl.style.display = "none";
    emptyEl.textContent = "Network error: " + err.message;
    emptyEl.style.display = "block";
  }
}

function renderFindings(containerId, findings) {
  const container = document.getElementById(containerId);
  container.innerHTML = findings.map(f => {
    const iconMap = { PASS: "&#10004;", WARNING: "&#9888;", VIOLATION: "&#10008;" };
    const clsMap  = { PASS: "pass",     WARNING: "warn",    VIOLATION: "fail" };
    return `
      <div class="finding-item">
        <span class="finding-icon ${clsMap[f.level]}">${iconMap[f.level]}</span>
        <span class="finding-code">${escHtml(f.code_ref)}</span>
        <span class="finding-desc">${escHtml(f.description)}</span>
      </div>`;
  }).join("");
}

// ---------------------------------------------------------------------------
// Generate PDF
// ---------------------------------------------------------------------------

document.getElementById("btn-generate").addEventListener("click", async () => {
  const btn = document.getElementById("btn-generate");
  const errEl = document.getElementById("generate-error");
  btn.disabled = true;
  document.getElementById("generate-label").textContent = "Generating PDF...";
  errEl.style.display = "none";

  try {
    const res  = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    const data = await res.json();

    if (!data.ok) throw new Error(data.error);

    const name = document.getElementById("project_name").value || "cv2_form";
    window.location.href = `/download/${data.token}?name=${encodeURIComponent(name)}`;

  } catch (err) {
    errEl.textContent = "Error generating PDF: " + err.message;
    errEl.style.display = "block";
  } finally {
    btn.disabled = false;
    document.getElementById("generate-label").textContent = "\u2193 Generate CV2 PDF Form";
  }
});

// ---------------------------------------------------------------------------
// Demo project loader
// ---------------------------------------------------------------------------

document.getElementById("btn-load-demo").addEventListener("click", () => {
  // Project info
  document.getElementById("project_name").value      = "Riverside Commerce Center";
  document.getElementById("project_number").value    = "2025-0312";
  document.getElementById("permit_number").value     = "BP-2025-00441";
  document.getElementById("prepared_by").value       = "Jane Architect, AIA";
  document.getElementById("architect_license").value = "CA-C-12345";
  document.getElementById("engineer_license").value  = "SE-67890";

  // Location
  document.getElementById("site_address").value   = "1200 River Road, Suite 100";
  document.getElementById("parcel_number").value  = "123-456-789-00";
  document.getElementById("city").value           = "Sacramento";
  document.getElementById("county").value         = "Sacramento County";
  document.getElementById("state").value          = "CA";
  document.getElementById("country").value        = "USA";
  document.getElementById("ibc_edition").value    = "2022";
  document.getElementById("irc_edition").value    = "2022";
  document.getElementById("local_amendments").value = "Sacramento City Amendments to 2022 CBC";
  document.getElementById("zoning_district").value  = "C-2";
  document.getElementById("state-note").style.display = "none";

  // Classification
  document.getElementById("risk_category").value     = "II";
  document.getElementById("construction_type").value = "V-A";
  updateRiskHint(); updateConstructionHint();

  // Occupancies
  document.querySelectorAll('input[name="occupancy_groups"]').forEach(cb => {
    cb.checked = (cb.value === "B" || cb.value === "M");
    cb.dispatchEvent(new Event("change"));
  });

  // Dimensions
  document.getElementById("stories_above_grade").value   = "3";
  document.getElementById("stories_below_grade").value   = "0";
  document.getElementById("building_height_ft").value    = "42";
  document.getElementById("total_floor_area_sqft").value = "24000";
  document.getElementById("footprint_sqft").value        = "8000";

  // Rooms
  document.getElementById("room-tbody").innerHTML = "";
  roomIndex = 0;
  [
    { name: "Ground Floor Retail", occupancy_group: "M", floor_area_sqft: 8000, occupant_load_factor: 30 },
    { name: "2nd Floor Office",    occupancy_group: "B", floor_area_sqft: 8000, occupant_load_factor: 100 },
    { name: "3rd Floor Office",    occupancy_group: "B", floor_area_sqft: 6500, occupant_load_factor: 100 },
    { name: "Lobby / Common",      occupancy_group: "B", floor_area_sqft: 1500, occupant_load_factor: 100 },
  ].forEach(r => addRoomRow(r));

  // Systems
  document.getElementById("sprinkler_system").checked  = true;
  document.getElementById("sprinkler_system").dispatchEvent(new Event("change"));
  document.getElementById("sprinkler_standard").value  = "NFPA 13";
  document.getElementById("fire_alarm_system").checked = true;
  document.getElementById("fire_alarm_system").dispatchEvent(new Event("change"));

  // ADA
  document.getElementById("ada_compliant").checked   = true;
  document.getElementById("accessible_route").checked= true;
  document.getElementById("total_parking_spaces").value       = "60";
  document.getElementById("accessible_parking_spaces").value  = "4";
  parkingHint();

  // Energy
  document.getElementById("energy_code").value  = "ASHRAE 90.1-2019 / Title 24-2022";
  document.getElementById("climate_zone").value = "3B";

  // Notes
  document.getElementById("additional_codes").value  = "ASCE 7-22, ACI 318-19";
  document.getElementById("special_conditions").value = "Site within 500-year flood zone. Finished floor elevation per FEMA requirements.";
  document.getElementById("variances_requested").value = "None";

  goStep(1);
  alert("Demo project loaded! Click through the steps to review, then hit Check Compliance.");
});

// ---------------------------------------------------------------------------
// Tooltips
// ---------------------------------------------------------------------------

const tooltipEl = document.getElementById("tooltip-popup");

document.querySelectorAll(".tooltip-icon").forEach(icon => {
  icon.addEventListener("mouseenter", e => {
    const key = icon.dataset.tip;
    const content = TOOLTIP_CONTENT[key];
    if (!content) return;
    tooltipEl.innerHTML = content;
    tooltipEl.style.display = "block";
    positionTooltip(e);
  });
  icon.addEventListener("mousemove", positionTooltip);
  icon.addEventListener("mouseleave", () => { tooltipEl.style.display = "none"; });
});

function positionTooltip(e) {
  const x = e.clientX + 12, y = e.clientY + 12;
  const pw = tooltipEl.offsetWidth, ph = tooltipEl.offsetHeight;
  tooltipEl.style.left = (x + pw > window.innerWidth  ? x - pw - 20 : x) + "px";
  tooltipEl.style.top  = (y + ph > window.innerHeight ? y - ph - 20 : y) + "px";
}


// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
