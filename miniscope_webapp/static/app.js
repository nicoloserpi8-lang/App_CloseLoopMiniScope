let manualCalibActive = false;
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
  manualCalibActive = s.manual_calib_active;
  $("btn-cancel-manual-calib").style.display = manualCalibActive ? "inline-block" : "none";
  $("manual-calib-status").textContent = manualCalibActive
  ? `Clicca il punto ${s.manual_calib_points_count + 1} di 4 sul video`
  : "";
  let camLine;
  if (s.phantom) {
    camLine = `⚠️ Nessuna camera reale trovata (indice tentato: ${s.cam_index_used}) — modalità PHANTOM attiva.`;
  } else if (!s.cam_resolution_match) {
    camLine = `⚠️ Camera trovata all'indice ${s.cam_index_used} ma risoluzione ${s.cam_w}x${s.cam_h} inattesa.`;
  } else {
    camLine = `✅ Camera OK — indice ${s.cam_index_used}, risoluzione ${s.cam_w}x${s.cam_h}.`;
  }
  document.getElementById("cam-status-line").textContent = camLine;
  if (document.activeElement !== document.getElementById("camera-mode-select"))
  document.getElementById("camera-mode-select").value = s.mode;
  if ($("mag")) $("mag").textContent = s.magnification.toFixed(3);
  if ($("pitch")) $("pitch").textContent = `${s.pitch_x.toFixed(2)} x ${s.pitch_y.toFixed(2)}`;
  if ($("fiberpx")) $("fiberpx").textContent = `${s.pixels_inside_fiber} (${s.fiber_pct}%)`;
  if ($("calib-status")) {
    $("calib-status").textContent = s.calibrated
      ? "Calibrated"
      : "Uncalibrated (using fallback mapping)";
  }

  if ($("shutter-status")) $("shutter-status").textContent = s.shutter_status;
  if ($("active-px")) $("active-px").textContent = s.active_led_pixels;
  if ($("max-px")) $("max-px").textContent = s.pixels_inside_fiber;

  const stimBtn = $("btn-stim");
  if (stimBtn) {
    stimBtn.textContent = s.is_stimulating ? "Stop stimulation" : "Start stimulation";
    stimBtn.classList.toggle("active-on", s.is_stimulating);
  }

  if ($("output-label")) {
    $("output-label").textContent =
      s.output_mode === "hardware" ? "Hardware MicroLED (HDMI)" : "Virtual MicroLED";
  }

  const freezeBtn = $("btn-freeze");
  if (freezeBtn) {
    freezeBtn.textContent = s.frozen ? "Unfreeze" : "Freeze";
    freezeBtn.classList.toggle("freeze-on", s.frozen);
  }

  const modeLabel = s.phantom
    ? "Virtual Miniscope (phantom)"
    : `Miniscope live [${s.mode}]`;
  const frozenTag = s.frozen ? " — FROZEN" : "";
  if ($("status-left")) {
    $("status-left").textContent =
      `${modeLabel}${frozenTag} — neurons: ${s.neurons} — active MicroLED pixels: ${s.active_led_pixels} / ${s.pixels_inside_fiber}`;
  }

 // Aggiorna l'indicatore in base al valore calcolato dal backend
  const radiusDisplay = $("radius-display");
  if (radiusDisplay) {
    const r = s.current_cmos_radius || 0;
    const targetPx = s.target_px || 0;
    const areaCmos = Math.round(Math.PI * r * r);

    if (r > 0) {
      radiusDisplay.textContent = `Raggio CMOS: ${r} px (~${areaCmos} px²) [Target: ${targetPx} px]`;
    } else {
      radiusDisplay.textContent = `Target: ${targetPx} MicroLED px`;
    }
  }

  // Non sovrascrivere i campi mentre l'utente li digita
  if (document.activeElement !== $("l1") && $("l1")) $("l1").value = s.l1;
  if (document.activeElement !== $("l2") && $("l2")) $("l2").value = s.l2;
  if (document.activeElement !== $("fiber") && $("fiber")) $("fiber").value = s.fiber_core_um;
  if (document.activeElement !== $("target-px") && $("target-px")) $("target-px").value = s.target_px;
  if (document.activeElement !== $("freq") && $("freq")) $("freq").value = s.freq_hz;
  if (document.activeElement !== $("duty") && $("duty")) $("duty").value = s.duty_pct;
  if (document.activeElement !== $("output-select") && $("output-select")) $("output-select").value = s.output_mode;
}

async function refreshStatus() {
  try {
    const res = await fetch("/status");
    const s = await res.json();
    applyStatus(s);
  } catch (e) {
    // Server non ancora pronto o offline
  }
}
setInterval(refreshStatus, 500);
refreshStatus();

document.getElementById("camera-mode-select").addEventListener("change", async () => {
  const res = await fetch("/api/set_camera_mode", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ mode: document.getElementById("camera-mode-select").value })
  });
  applyStatus(await res.json());
});

document.getElementById("btn-check-monitors").addEventListener("click", async () => {
  const res = await fetch("/api/monitors");
  const data = await res.json();
  const el = document.getElementById("monitors-status");
  if (!data.ok) { el.textContent = `Errore: ${data.error}`; return; }
  el.textContent = data.count < 2
    ? `⚠️ Solo ${data.count} monitor rilevato/i.`
    : `✅ ${data.count} monitor rilevati.`;
});

// ---------------- Optics & Calibration ----------------
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
if ($("l1")) $("l1").addEventListener("input", sendLenses);
if ($("l2")) $("l2").addEventListener("input", sendLenses);

const sendFiber = debounce(() => {
  postJSON("/api/set_fiber", { fiber_um: parseFloat($("fiber").value) }).then(applyStatus);
}, 350);
if ($("fiber")) $("fiber").addEventListener("input", sendFiber);

$("btn-manual-calib").addEventListener("click", async () => {
  const s = await postJSON("/api/start_manual_calibration", {});
  applyStatus(s);
});
$("btn-cancel-manual-calib").addEventListener("click", async () => {
  const s = await postJSON("/api/cancel_manual_calibration", {});
  applyStatus(s);
});

if ($("btn-calibrate")) {
  $("btn-calibrate").addEventListener("click", async () => {
  $("btn-calibrate").disabled = true;
  $("btn-calibrate").textContent = "Calibrating…";
  await postJSON("/api/calibrate", {});
  const waitDone = async () => {
    const res = await fetch("/status");
    const s = await res.json();
    applyStatus(s);
    if (s.calibrating) {
      setTimeout(waitDone, 300);
    } else {
      $("btn-calibrate").disabled = false;
      $("btn-calibrate").textContent = "Calibrate";
    }
  };
  waitDone();
});
}

// ---------------- Stimulation ----------------
const sendTargetPx = debounce(() => {
  postJSON("/api/set_target_px", { value: parseInt($("target-px").value, 10) }).then(applyStatus);
}, 350);
if ($("target-px")) $("target-px").addEventListener("input", sendTargetPx);

const sendFreq = debounce(() => {
  postJSON("/api/set_freq", { value: parseFloat($("freq").value) }).then(applyStatus);
}, 350);
if ($("freq")) $("freq").addEventListener("input", sendFreq);

const sendDuty = debounce(() => {
  postJSON("/api/set_duty", { value: parseFloat($("duty").value) }).then(applyStatus);
}, 350);
if ($("duty")) $("duty").addEventListener("input", sendDuty);

if ($("btn-stim")) {
  $("btn-stim").addEventListener("click", async () => {
    const s = await postJSON("/api/toggle_stim", {});
    applyStatus(s);
  });
}

if ($("btn-clear-neurons")) {
  $("btn-clear-neurons").addEventListener("click", async () => {
    const s = await postJSON("/api/clear_rois", {});
    applyStatus(s);
  });
}

// ---------------- MicroLED Output ----------------
if ($("output-select")) {
  $("output-select").addEventListener("change", async () => {
    const s = await postJSON("/api/set_output", { mode: $("output-select").value });
    applyStatus(s);
  });
}

// ---------------- Video: ROI Click & Drag / Zoom / Pan ----------------
const cmosImg = $("cmos-img");
const roiPreview = $("roi-preview");
const DRAG_THRESHOLD_PX = 5;

function relativeCoords(evt) {
  const rect = cmosImg.getBoundingClientRect();
  const x = ((evt.clientX - rect.left) / rect.width) * cmosImg.naturalWidth || (evt.clientX - rect.left);
  const y = ((evt.clientY - rect.top) / rect.height) * cmosImg.naturalHeight || (evt.clientY - rect.top);
  return { x, y };
}

let dragStartScreen = null;
let dragStartImg = null;
let isDraggingRoi = false;

function showPreviewCircle(cx, cy, r) {
  if (roiPreview) {
    roiPreview.innerHTML = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#ffe14d" stroke-width="1.5" stroke-dasharray="4 3"/>`;
  }
}
function clearPreviewCircle() {
  if (roiPreview) roiPreview.innerHTML = "";
}

// Evento Mousedown RIVATTIVATO
if (cmosImg) {
  cmosImg.addEventListener("dragstart", (e) => e.preventDefault()); // Previene il drag nativo

  cmosImg.addEventListener("mousedown", (evt) => {
    if (manualCalibActive) return;
    if (evt.button !== 0 || evt.shiftKey) return;
    const rect = cmosImg.getBoundingClientRect();
    dragStartScreen = { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
    dragStartImg = relativeCoords(evt);
    isDraggingRoi = true;
  });

  cmosImg.addEventListener("click", async (evt) => {
    if (!manualCalibActive) return;
    const { x, y } = relativeCoords(evt);
    const s = await postJSON("/api/add_manual_calib_point", { x, y });
    applyStatus(s);
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
}

window.addEventListener("mousemove", (evt) => {
  if (!isDraggingRoi || !dragStartScreen || !cmosImg) return;
  const rect = cmosImg.getBoundingClientRect();
  const curX = evt.clientX - rect.left;
  const curY = evt.clientY - rect.top;
  const r = Math.hypot(curX - dragStartScreen.x, curY - dragStartScreen.y);
  if (r > DRAG_THRESHOLD_PX) {
    showPreviewCircle(dragStartScreen.x, dragStartScreen.y, r);
  }
});

window.addEventListener("mouseup", async (evt) => {
  if (!isDraggingRoi || !dragStartImg || !cmosImg) return;
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
    const endImg = relativeCoords(evt);
    s = await postJSON("/api/add_roi_drag", {
      x1: dragStartImg.x, y1: dragStartImg.y, x2: endImg.x, y2: endImg.y,
    });
  } else {
    s = await postJSON("/api/add_roi", { x: dragStartImg.x, y: dragStartImg.y });
  }
  applyStatus(s);
  dragStartScreen = null;
  dragStartImg = null;
});

// ---------------- Pan (Shift + Click oppure Tasto Centrale) ----------------
let isPanning = false;
let panStart = null;
if (cmosImg) {
  cmosImg.addEventListener("mousedown", (evt) => {
    if (evt.button === 1 || (evt.button === 0 && evt.shiftKey)) {
      isPanning = true;
      panStart = { x: evt.clientX, y: evt.clientY };
      evt.preventDefault();
    }
  });
}
window.addEventListener("mousemove", async (evt) => {
  if (!isPanning || !panStart) return;
  const dx = evt.clientX - panStart.x;
  const dy = evt.clientY - panStart.y;
  panStart = { x: evt.clientX, y: evt.clientY };
  await postJSON("/api/pan", { dx, dy });
});
window.addEventListener("mouseup", () => { isPanning = false; panStart = null; });

if ($("btn-reset-zoom")) {
  $("btn-reset-zoom").addEventListener("click", async () => {
    const s = await postJSON("/api/reset_zoom", {});
    applyStatus(s);
  });
}

// ---------------- Freeze & Raggio ----------------
if ($("btn-freeze")) {
  $("btn-freeze").addEventListener("click", async () => {
    const s = await postJSON("/api/toggle_freeze", {});
    applyStatus(s);
  });
}

document.addEventListener("keydown", async (evt) => {
  if (evt.code === "Space" && evt.target === document.body) {
    evt.preventDefault();
    const s = await postJSON("/api/toggle_freeze", {});
    applyStatus(s);
  }
});

