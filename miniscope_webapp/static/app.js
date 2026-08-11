const $ = (id) => document.getElementById(id);

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

function applyStatus(s) {
  $("mag").textContent = s.magnification.toFixed(3);
  $("pitch").textContent = `${s.pitch_x.toFixed(2)} x ${s.pitch_y.toFixed(2)}`;
  $("fiberpx").textContent = `${s.pixels_inside_fiber} (${s.fiber_pct}%)`;
  $("calib-status").textContent = s.calibrated
    ? "Calibrated"
    : "Uncalibrated (using fallback mapping)";

  $("shutter-status").textContent = s.shutter_status;
  $("active-px").textContent = s.active_led_pixels;
  $("max-px").textContent = s.pixels_inside_fiber;

  const stimBtn = $("btn-stim");
  stimBtn.textContent = s.is_stimulating ? "Stop stimulation" : "Start stimulation";
  stimBtn.classList.toggle("active-on", s.is_stimulating);

  $("output-label").textContent =
    s.output_mode === "hardware" ? "Hardware MicroLED (HDMI)" : "Virtual MicroLED";

  $("btn-freeze").textContent = s.frozen ? "Unfreeze" : "Freeze";
  $("btn-freeze").classList.toggle("freeze-on", s.frozen);

  const modeLabel = s.phantom
    ? "Virtual Miniscope (phantom)"
    : `Miniscope live [${s.mode}]`;
  const frozenTag = s.frozen ? " — FROZEN" : "";
  $("status-left").textContent =
    `${modeLabel}${frozenTag} — neurons: ${s.neurons} — active MicroLED pixels: ${s.active_led_pixels} / ${s.pixels_inside_fiber}`;

  // non sovrascrivere i campi numerici mentre l'utente li sta modificando
  if (document.activeElement !== $("l1")) $("l1").value = s.l1;
  if (document.activeElement !== $("l2")) $("l2").value = s.l2;
  if (document.activeElement !== $("fiber")) $("fiber").value = s.fiber_core_um;
  if (document.activeElement !== $("target-px")) $("target-px").value = s.target_px;
  if (document.activeElement !== $("freq")) $("freq").value = s.freq_hz;
  if (document.activeElement !== $("duty")) $("duty").value = s.duty_pct;
  if (document.activeElement !== $("output-select")) $("output-select").value = s.output_mode;
}

async function refreshStatus() {
  try {
    const res = await fetch("/status");
    const s = await res.json();
    applyStatus(s);
  } catch (e) {
    // server non ancora pronto o offline: riprova al prossimo tick
  }
}
setInterval(refreshStatus, 500);
refreshStatus();

// ---------------- Optics & calibration ----------------
function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

const sendLenses = debounce(() => {
  postJSON("/api/set_lenses", { l1: parseFloat($("l1").value), l2: parseFloat($("l2").value) })
    .then(applyStatus);
}, 350);
$("l1").addEventListener("input", sendLenses);
$("l2").addEventListener("input", sendLenses);

const sendFiber = debounce(() => {
  postJSON("/api/set_fiber", { fiber_um: parseFloat($("fiber").value) }).then(applyStatus);
}, 350);
$("fiber").addEventListener("input", sendFiber);

$("btn-calibrate").addEventListener("click", async () => {
  $("btn-calibrate").textContent = "Calibrating…";
  const s = await postJSON("/api/calibrate", {});
  applyStatus(s);
  $("btn-calibrate").textContent = "Calibrate";
});

// ---------------- Stimulation ----------------
const sendTargetPx = debounce(() => {
  postJSON("/api/set_target_px", { value: parseInt($("target-px").value, 10) }).then(applyStatus);
}, 350);
$("target-px").addEventListener("input", sendTargetPx);

const sendFreq = debounce(() => {
  postJSON("/api/set_freq", { value: parseFloat($("freq").value) }).then(applyStatus);
}, 350);
$("freq").addEventListener("input", sendFreq);

const sendDuty = debounce(() => {
  postJSON("/api/set_duty", { value: parseFloat($("duty").value) }).then(applyStatus);
}, 350);
$("duty").addEventListener("input", sendDuty);

$("btn-stim").addEventListener("click", async () => {
  const s = await postJSON("/api/toggle_stim", {});
  applyStatus(s);
});

$("btn-clear-neurons").addEventListener("click", async () => {
  const s = await postJSON("/api/clear_rois", {});
  applyStatus(s);
});

// ---------------- MicroLED output ----------------
$("output-select").addEventListener("change", async () => {
  const s = await postJSON("/api/set_output", { mode: $("output-select").value });
  applyStatus(s);
});

// ---------------- Video: click = ROI raggio auto, drag = ROI raggio manuale, ----------------
// tasto destro = elimina ultima, rotella = zoom (replica main.py + ROI_Microled_selector.py)
const cmosImg = $("cmos-img");
const roiPreview = $("roi-preview");
const DRAG_THRESHOLD_PX = 5;

function relativeCoords(evt) {
  const rect = cmosImg.getBoundingClientRect();
  const x = ((evt.clientX - rect.left) / rect.width) * cmosImg.naturalWidth || (evt.clientX - rect.left);
  const y = ((evt.clientY - rect.top) / rect.height) * cmosImg.naturalHeight || (evt.clientY - rect.top);
  return { x, y };
}

let dragStartScreen = null; // coordinate schermo (px) per la preview SVG
let dragStartImg = null;    // coordinate immagine (naturalWidth/Height) per l'invio al backend
let isDraggingRoi = false;

function showPreviewCircle(cx, cy, r) {
  roiPreview.innerHTML = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#ffe14d" stroke-width="1.5" stroke-dasharray="4 3"/>`;
}
function clearPreviewCircle() { roiPreview.innerHTML = ""; }

cmosImg.addEventListener("mousedown", (evt) => {
  if (evt.button !== 0 || evt.shiftKey) return; // il tasto sinistro semplice avvia il ciclo click/drag
  const rect = cmosImg.getBoundingClientRect();
  dragStartScreen = { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
  dragStartImg = relativeCoords(evt);
  isDraggingRoi = true;
});

window.addEventListener("mousemove", (evt) => {
  if (!isDraggingRoi || !dragStartScreen) return;
  const rect = cmosImg.getBoundingClientRect();
  const curX = evt.clientX - rect.left;
  const curY = evt.clientY - rect.top;
  const r = Math.hypot(curX - dragStartScreen.x, curY - dragStartScreen.y);
  if (r > DRAG_THRESHOLD_PX) {
    showPreviewCircle(dragStartScreen.x, dragStartScreen.y, r);
  }
});

window.addEventListener("mouseup", async (evt) => {
  if (!isDraggingRoi || !dragStartImg) return;
  isDraggingRoi = false;
  clearPreviewCircle();

  const rect = cmosImg.getBoundingClientRect();
  const withinImage =
    evt.clientX >= rect.left && evt.clientX <= rect.right &&
    evt.clientY >= rect.top && evt.clientY <= rect.bottom;
  if (!withinImage) { dragStartScreen = null; dragStartImg = null; return; }

  const screenDx = (evt.clientX - rect.left) - dragStartScreen.x;
  const screenDy = (evt.clientY - rect.top) - dragStartScreen.y;
  const screenDist = Math.hypot(screenDx, screenDy);

  let s;
  if (screenDist > DRAG_THRESHOLD_PX) {
    // drag: raggio manuale, come ROI_Microled_selector.py
    const endImg = relativeCoords(evt);
    s = await postJSON("/api/add_roi_drag", {
      x1: dragStartImg.x, y1: dragStartImg.y, x2: endImg.x, y2: endImg.y,
    });
  } else {
    // click semplice: raggio automatico, come main.py
    s = await postJSON("/api/add_roi", { x: dragStartImg.x, y: dragStartImg.y });
  }
  applyStatus(s);
  dragStartScreen = null;
  dragStartImg = null;
});

cmosImg.addEventListener("contextmenu", async (evt) => {
  evt.preventDefault();
  const s = await postJSON("/api/remove_last_roi", {});
  applyStatus(s);
});

cmosImg.addEventListener("wheel", async (evt) => {
  evt.preventDefault();
  const { x, y } = relativeCoords(evt);
  const delta = evt.deltaY < 0 ? 1 : -1;
  const s = await postJSON("/api/zoom", { delta, x, y });
  applyStatus(s);
}, { passive: false });

// pan con tasto centrale / trascinamento con shift premuto
let isPanning = false;
let panStart = null;
cmosImg.addEventListener("mousedown", (evt) => {
  if (evt.button === 1 || (evt.button === 0 && evt.shiftKey)) {
    isPanning = true;
    panStart = { x: evt.clientX, y: evt.clientY };
    evt.preventDefault();
  }
});
window.addEventListener("mousemove", async (evt) => {
  if (!isPanning || !panStart) return;
  const dx = evt.clientX - panStart.x;
  const dy = evt.clientY - panStart.y;
  panStart = { x: evt.clientX, y: evt.clientY };
  await postJSON("/api/pan", { dx, dy });
});
window.addEventListener("mouseup", () => { isPanning = false; panStart = null; });

$("btn-reset-zoom").addEventListener("click", async () => {
  const s = await postJSON("/api/reset_zoom", {});
  applyStatus(s);
});

// ---------------- Freeze frame (equivalente a [SPACE] in ROI_Microled_selector.py) ----------------
$("btn-freeze").addEventListener("click", async () => {
  const s = await postJSON("/api/toggle_freeze", {});
  applyStatus(s);
});
document.addEventListener("keydown", async (evt) => {
  if (evt.code === "Space" && evt.target === document.body) {
    evt.preventDefault();
    const s = await postJSON("/api/toggle_freeze", {});
    applyStatus(s);
  }
});

// ---------------- Radius +/- (equivalente a [+]/[-] in ROI_Microled_selector.py) ----------------
$("btn-radius-plus").addEventListener("click", async () => {
  const s = await postJSON("/api/bump_radius", { delta: 2 });
  applyStatus(s);
});
$("btn-radius-minus").addEventListener("click", async () => {
  const s = await postJSON("/api/bump_radius", { delta: -2 });
  applyStatus(s);
});
