"""
NPN Miniscope - Web Control Interface
======================================
Backend Flask che espone via browser lo stesso sistema di controllo
closed-loop presente in MAIN.py, riusando senza modifiche i moduli:
OPTICS_CONFIG, SHUTTER_CONTROL, CALIBRATOR, HARDWARE_UTILS.

Avvio:
    pip install -r requirements.txt
    python app.py
Poi apri http://127.0.0.1:5000 nel browser.
"""

import base64
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request

from CALIBRATOR import DualMicroLEDCalibrator
from HARDWARE_UTILS import find_miniscope_cam_index_smart, get_jdb_monitor_coords
from OPTICS_CONFIG import OpticsConfig
from SHUTTER_CONTROL import ShutterController

app = Flask(__name__)

# ============================================================
#  SYSTEM STATE
# ============================================================
class MiniscopeSystem:
    def __init__(self):
        self.lock = threading.RLock()

        self.mode_name = "PC"          # "PC" or "RIG"
        self.cam_w, self.cam_h = 640, 480
        self.cap = None
        self.phantom_mode = True
        self._phantom_blobs = self._make_phantom_blobs()

        self.optics = OpticsConfig(mode=self.mode_name)
        self.shutters = ShutterController(port="COM3", dummy_mode=True)
        self.calibrator = DualMicroLEDCalibrator(self.optics)

        self.jdb_fiber_mask, self.max_fiber_pixels, self.fiber_pct = (
            self.optics.get_valid_fiber_mask()
        )

        # ROI / selected neurons (x_cmos, y_cmos, raggio_px)
        self.selected_rois = []
        self.target_microled_pixels = 120
        self.current_cmos_radius = 12

        # Zoom / pan
        self.zoom_scale = 1.0
        self.zoom_center_x = None
        self.zoom_center_y = None

        # Stimolazione
        self.freq_hz = 0.10
        self.duty_cycle_pct = 50.0
        self.is_stimulating = False

        # Calibrazione
        self.M_cam2led = None
        self.M_led2cam = None
        self.calibrated = False

        # Output MicroLED: "virtual" (solo preview browser) o "hardware"
        self.output_mode = "virtual"
        self.jdb_win_name = "MICROLED_DISPLAY_HDMI"
        self._hdmi_window_open = False

        # Frame correnti (JPEG bytes) condivisi tra thread di elaborazione e le route Flask
        self.latest_cmos_jpeg = None
        self.latest_jdb_jpeg = None

        self._init_camera()
        self._rebuild_base_frames()
        self._running = True
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()

    # ---------------- camera ----------------
    def _make_phantom_blobs(self):
        rng = np.random.default_rng(42)
        blobs = []
        for _ in range(16):
            x = rng.uniform(0.15, 0.85)
            y = rng.uniform(0.15, 0.85)
            r = rng.uniform(4, 11)
            amp = rng.uniform(120, 255)
            blobs.append([x, y, r, amp])
        return blobs

    def _init_camera(self):
        if self.mode_name == "PC":
            target_w, target_h = 640, 480
            cam_index = 0
        else:
            target_w, target_h = 608, 608
            cam_index = find_miniscope_cam_index_smart(mode=self.mode_name)

        self.cam_index_used = cam_index

        cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)

        ok = cap.isOpened()
        frame = None
        if ok:
            ret, frame = cap.read()
            ok = ret and frame is not None

        if ok:
            self.cap = cap
            self.cam_h, self.cam_w = frame.shape[:2]
            self.phantom_mode = False
        else:
            if cap is not None:
                cap.release()
            self.cap = None
            self.cam_w, self.cam_h = target_w, target_h
            self.phantom_mode = True
            self.cam_resolution_match = False

        self.optics.set_mode(self.mode_name)

    def set_camera_mode(self, mode):
        with self.lock:
            if self.cap is not None:
                self.cap.release()
            self.mode_name = "RIG" if mode.upper() == "RIG" else "PC"
            self._init_camera()
            self.M_cam2led = None
            self.M_led2cam = None
            self.calibrated = False
            self.zoom_scale = 1.0
            self.zoom_center_x, self.zoom_center_y = None, None

    def _generate_phantom_frame(self):
        """Genera un frame sintetico in stile CMOS con 'neuroni' luminosi, per demo senza hardware."""
        t = time.time()
        img = np.zeros((self.cam_h, self.cam_w), dtype=np.uint8)
        noise = (np.random.default_rng().normal(6, 3, img.shape)).clip(0, 255)
        img[:] = noise.astype(np.uint8)

        for i, (fx, fy, r, amp) in enumerate(self._phantom_blobs):
            jitter_x = 3 * np.sin(t * 0.3 + i)
            jitter_y = 3 * np.cos(t * 0.25 + i * 1.3)
            cx = int(fx * self.cam_w + jitter_x)
            cy = int(fy * self.cam_h + jitter_y)
            flicker = 0.75 + 0.25 * np.sin(t * 1.7 + i * 2.1)
            cv2.circle(img, (cx, cy), int(r), int(amp * flicker), -1, lineType=cv2.LINE_AA)
        img = cv2.GaussianBlur(img, (5, 5), 0)
        return img

    def read_frame_gray(self):
        if getattr(self, "frozen", False) and getattr(self, "_last_gray", None) is not None:
            return self._last_gray
        if self.phantom_mode or self.cap is None:
            gray = self._generate_phantom_frame()
        else:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                gray = self._generate_phantom_frame()
            else:
                self.cam_h, self.cam_w = frame.shape[:2]
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        self._last_gray = gray
        return gray

    # ---------------- optics-dependent frames ----------------
    def _rebuild_base_frames(self):
        self.jdb_fiber_mask, self.max_fiber_pixels, self.fiber_pct = (
            self.optics.get_valid_fiber_mask()
        )
        f_blue = np.zeros((self.optics.jdb_h_px, self.optics.jdb_w_px, 3), dtype=np.uint8)
        f_blue[:, :, 0] = self.jdb_fiber_mask
        f_red = np.zeros((self.optics.jdb_h_px, self.optics.jdb_w_px, 3), dtype=np.uint8)
        f_red[:, :, 0] = self.jdb_fiber_mask
        self.frame_blue_only = f_blue
        self.frame_red_only = f_red

    def _ensure_homography(self):
        if self.M_cam2led is not None:
            return
        cam_w, cam_h = self.cam_w, self.cam_h
        pts_cam = np.float32(
            [
                [cam_w * 0.1, cam_h * 0.1],
                [cam_w * 0.9, cam_h * 0.1],
                [cam_w * 0.9, cam_h * 0.9],
                [cam_w * 0.1, cam_h * 0.9],
            ]
        )
        pts_jdb = np.float32(
            [[0, 0], [self.optics.jdb_w_px, 0],
             [self.optics.jdb_w_px, self.optics.jdb_h_px], [0, self.optics.jdb_h_px]]
        )
        self.M_cam2led = cv2.getPerspectiveTransform(pts_cam, pts_jdb)
        self.M_led2cam = cv2.getPerspectiveTransform(pts_jdb, pts_cam)
        self._update_cmos_radius()

    def _update_cmos_radius(self):
        if self.M_cam2led is None:
            self.current_cmos_radius = 12
            return
        r_test = 10
        test_mask = np.zeros((self.cam_h, self.cam_w), dtype=np.uint8)
        cv2.circle(test_mask, (self.cam_w // 2, self.cam_h // 2), r_test, 255, -1)
        test_target = cv2.warpPerspective(
            test_mask, self.M_cam2led, (self.optics.jdb_w_px, self.optics.jdb_h_px),
            flags=cv2.INTER_NEAREST,
        )
        measured = np.count_nonzero(test_target)
        area = np.pi * (r_test ** 2)
        if measured > 0:
            ratio = measured / area
            required_area = self.target_microled_pixels / ratio
            radius = np.sqrt(required_area / np.pi)
            self.current_cmos_radius = max(1, int(np.round(radius)))
        else:
            self.current_cmos_radius = 12

    # ---------------- zoom helpers ----------------
    def screen_to_cmos(self, x_disp, y_disp):
        if self.zoom_center_x is None or self.zoom_center_y is None:
            return x_disp, y_disp
        cam_w, cam_h = self.cam_w, self.cam_h
        crop_w = cam_w / self.zoom_scale
        crop_h = cam_h / self.zoom_scale
        x1 = max(0, min(cam_w - crop_w, self.zoom_center_x - crop_w / 2))
        y1 = max(0, min(cam_h - crop_h, self.zoom_center_y - crop_h / 2))
        real_x = int(x1 + (x_disp / cam_w) * crop_w)
        real_y = int(y1 + (y_disp / cam_h) * crop_h)
        return real_x, real_y

    def apply_zoom_crop(self, img):
        if self.zoom_scale <= 1.0 or self.zoom_center_x is None:
            return img
        cam_w, cam_h = self.cam_w, self.cam_h
        crop_w = cam_w / self.zoom_scale
        crop_h = cam_h / self.zoom_scale
        x1 = int(max(0, min(cam_w - crop_w, self.zoom_center_x - crop_w / 2)))
        y1 = int(max(0, min(cam_h - crop_h, self.zoom_center_y - crop_h / 2)))
        x2, y2 = int(x1 + crop_w), int(y1 + crop_h)
        cropped = img[y1:y2, x1:x2]
        if cropped.size == 0:
            return img
        return cv2.resize(cropped, (cam_w, cam_h), interpolation=cv2.INTER_LINEAR)

    # ---------------- actions (chiamate dalle route) ----------------
    def add_roi(self, x_disp, y_disp):
        with self.lock:
            real_x, real_y = self.screen_to_cmos(x_disp, y_disp)
            real_x, real_y = int(real_x), int(real_y)
            if 0 <= real_x < self.cam_w and 0 <= real_y < self.cam_h:
                # Usa sempre il raggio calcolato in base al target di pixel MicroLED
                self.selected_rois.append((real_x, real_y, int(self.current_cmos_radius)))

    def add_roi_drag(self, x1_disp, y1_disp, x2_disp, y2_disp):
        """Calcola il raggio in base al trascinamento per questa specifica ROI."""
        with self.lock:
            cx, cy = self.screen_to_cmos(x1_disp, y1_disp)
            ex, ey = self.screen_to_cmos(x2_disp, y2_disp)
            cx, cy = int(cx), int(cy)
            radius = max(4, int(np.hypot(ex - cx, ey - cy)))
            if 0 <= cx < self.cam_w and 0 <= cy < self.cam_h:
                self.selected_rois.append((cx, cy, radius))

    def bump_manual_radius(self, delta):
        with self.lock:
            r = getattr(self, "manual_radius", self.current_cmos_radius)
            self.manual_radius = max(2, r + delta)
            return self.manual_radius

    def toggle_freeze(self):
        with self.lock:
            self.frozen = not getattr(self, "frozen", False)
            return self.frozen

    def remove_last_roi(self):
        with self.lock:
            if self.selected_rois:
                self.selected_rois.pop()

    def clear_rois(self):
        with self.lock:
            self.selected_rois.clear()

    def set_target_pixels(self, value):
        with self.lock:
            self.target_microled_pixels = max(1, int(value))
            self._update_cmos_radius()

    def set_frequency(self, value):
        with self.lock:
            if value > 0:
                self.freq_hz = float(value)

    def set_duty_cycle(self, value):
        with self.lock:
            if 0 < value <= 100:
                self.duty_cycle_pct = float(value)

    def set_lenses(self, l1, l2):
        with self.lock:
            if l1 > 0 and l2 > 0:
                self.optics.update_lenses(l1, l2)
                self._rebuild_base_frames()
                self._update_cmos_radius()

    def set_fiber_core(self, core_um):
        with self.lock:
            if core_um > 0:
                self.optics.update_fiber_core(core_um)
                self._rebuild_base_frames()
                self._update_cmos_radius()

    def toggle_stimulation(self):
        with self.lock:
            self.is_stimulating = not self.is_stimulating
            if self.is_stimulating:
                self.shutters.start_interleaved_pulsing(self.freq_hz, self.duty_cycle_pct)
            else:
                self.shutters.close_all()
            return self.is_stimulating

    def reset_zoom(self):
        with self.lock:
            self.zoom_scale = 1.0
            self.zoom_center_x, self.zoom_center_y = self.cam_w / 2, self.cam_h / 2

    def apply_zoom(self, delta, x_disp, y_disp):
        with self.lock:
            if self.zoom_center_x is None:
                self.zoom_center_x, self.zoom_center_y = self.cam_w / 2, self.cam_h / 2
            if delta > 0:
                self.zoom_scale = min(10.0, self.zoom_scale * 1.25)
            else:
                self.zoom_scale = max(1.0, self.zoom_scale / 1.25)
            real_x, real_y = self.screen_to_cmos(x_disp, y_disp)
            self.zoom_center_x, self.zoom_center_y = real_x, real_y

    def pan(self, dx, dy):
        with self.lock:
            if self.zoom_center_x is None:
                self.zoom_center_x, self.zoom_center_y = self.cam_w / 2, self.cam_h / 2
            self.zoom_center_x = max(0, min(self.cam_w, self.zoom_center_x - dx / self.zoom_scale))
            self.zoom_center_y = max(0, min(self.cam_h, self.zoom_center_y - dy / self.zoom_scale))

    def run_calibration(self):
        with self.lock:
            if self.phantom_mode or self.cap is None:
                # In modalità phantom simuliamo una calibrazione riuscita con mapping di default
                self._ensure_homography()
                self.calibrated = True
                return True
            M_cam2led, M_led2cam, success = self.calibrator.run_full_calibration(
                self.cap, self.jdb_win_name if self._hdmi_window_open else "MICROLED_DISPLAY_HDMI"
            )
            if M_cam2led is not None:
                self.M_cam2led = M_cam2led
                self.M_led2cam = M_led2cam
                self._update_cmos_radius()
                self.calibrated = success
            return success

    #def set_output_mode(self, mode):
        #with self.lock:
            #self.output_mode = "hardware" if mode == "hardware" else "virtual"
            #print(
                #f"[OUTPUT] Richiesta ricevuta: mode='{mode}' -> output_mode='{self.output_mode}', hdmi_gia_aperta={self._hdmi_window_open}")  # NUOVO
            #if self.output_mode == "hardware" and not self._hdmi_window_open:
                #try:
                    #jdb_x, jdb_y, disp_w, disp_h = get_jdb_monitor_coords(jdb_monitor_index=1)
                    #print(f"[OUTPUT] Monitor 2 rilevato: x={jdb_x}, y={jdb_y}, w={disp_w}, h={disp_h}")  # NUOVO
                    #cv2.namedWindow(self.jdb_win_name, cv2.WINDOW_NORMAL)
                    #cv2.moveWindow(self.jdb_win_name, jdb_x, jdb_y)
                    #cv2.setWindowProperty(self.jdb_win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                    #self._hdmi_window_open = True
                    #print("[OUTPUT] Finestra HDMI aperta con successo")  # NUOVO
                #except Exception as e:
                    #print(f"[WARN] Impossibile aprire finestra HDMI reale: {e}")
                    #self.output_mode = "virtual"

    def set_output_mode(self, mode):
        with self.lock:
            self.output_mode = "hardware" if mode == "hardware" else "virtual"
            # La finestra cv2 viene creata/aggiornata solo dentro _loop(),
            # sempre sullo stesso thread, per evitare problemi HighGUI multi-thread su Windows.

    # ---------------- main processing loop ----------------
    def _loop(self):
        while self._running:
            with self.lock:
                self._ensure_homography()
                gray = self.read_frame_gray()
                cam_w, cam_h = self.cam_w, self.cam_h
                canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

                # contorno fibra ottica proiettato sul CMOS
                cmos_fiber_mask = cv2.warpPerspective(self.jdb_fiber_mask, self.M_led2cam, (cam_w, cam_h))
                contours, _ = cv2.findContours(cmos_fiber_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(canvas, contours, -1, (255, 200, 0), 2)

                microled_pattern = np.zeros((self.optics.jdb_h_px, self.optics.jdb_w_px), dtype=np.uint8)

                for idx, (rx, ry, rr) in enumerate(self.selected_rois):
                    single_mask = np.zeros((cam_h, cam_w), dtype=np.uint8)
                    cv2.circle(single_mask, (rx, ry), rr, 255, -1)
                    single_target = cv2.warpPerspective(
                        single_mask, self.M_cam2led,
                        (self.optics.jdb_w_px, self.optics.jdb_h_px), flags=cv2.INTER_NEAREST,
                    )
                    single_valid = cv2.bitwise_and(single_target, self.jdb_fiber_mask)
                    px_count = np.count_nonzero(single_valid)
                    microled_pattern = cv2.bitwise_or(microled_pattern, single_valid)

                    cv2.circle(canvas, (rx, ry), rr, (0, 255, 0), 2)
                    lbl = f"N{idx + 1}: {px_count}px"
                    cv2.putText(canvas, lbl, (rx - 20, ry + rr + 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2)
                    cv2.putText(canvas, lbl, (rx - 20, ry + rr + 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

                cmos_stim_area = cv2.warpPerspective(
                    microled_pattern, self.M_led2cam, (cam_w, cam_h), flags=cv2.INTER_NEAREST
                )
                canvas[cmos_stim_area > 0] = [0, 0, 255]
                self.frame_red_only[:, :, 2] = microled_pattern
                self.active_led_pixels = int(np.count_nonzero(microled_pattern))

                status = f"STIM: {'ON' if self.is_stimulating else 'OFF'} | Freq: {self.freq_hz:.2f}Hz | Duty: {self.duty_cycle_pct:.0f}% | Target: {self.target_microled_pixels}px"
                cv2.putText(canvas, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

                display_canvas = self.apply_zoom_crop(canvas)

                # scelta pattern JDB corrente (blink stimolazione)
                if self.is_stimulating:
                    period = 1.0 / self.freq_hz if self.freq_hz > 0 else 1.0
                    t_red_on = period * (self.duty_cycle_pct / 100.0)
                    time_in_cycle = time.time() % period
                    if time_in_cycle < t_red_on:
                        self.shutters.set_both_on()
                        jdb_frame = self.frame_red_only
                        self.shutter_status = "Both (Red+Blue)"
                    else:
                        self.shutters.set_blue_only()
                        jdb_frame = self.frame_blue_only
                        self.shutter_status = "Blue only"
                else:
                    self.shutters.set_blue_only()
                    jdb_frame = self.frame_blue_only
                    self.shutter_status = "Blue only"

                #if self.output_mode == "hardware" and self._hdmi_window_open:
                    #if not getattr(self, "_hdmi_debug_printed", False):
                        #print(f"[OUTPUT] Primo invio frame a schermo 2, shape={jdb_frame.shape}")  # NUOVO
                        #self._hdmi_debug_printed = True
                    #try:
                        #cv2.imshow(self.jdb_win_name, jdb_frame)
                        #cv2.waitKey(1)
                    #except Exception as e:
                        #print(f"[HDMI ERROR] {e}")

                if self.output_mode == "hardware":
                    if not self._hdmi_window_open:
                        try:
                            jdb_x, jdb_y, disp_w, disp_h = get_jdb_monitor_coords(jdb_monitor_index=1)
                            cv2.namedWindow(self.jdb_win_name, cv2.WINDOW_NORMAL)
                            cv2.moveWindow(self.jdb_win_name, jdb_x, jdb_y)
                            cv2.setWindowProperty(self.jdb_win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                            self._hdmi_window_open = True
                            print(f"[OUTPUT] Finestra HDMI creata su schermo 2 (x={jdb_x}, y={jdb_y})")
                        except Exception as e:
                            print(f"[HDMI ERROR] Creazione finestra fallita: {e}")
                            self.output_mode = "virtual"
                    if self._hdmi_window_open:
                        try:
                            jdb_frame_rotated = cv2.rotate(jdb_frame, cv2.ROTATE_90_CLOCKWISE)  # NUOVO
                            cv2.imshow(self.jdb_win_name, jdb_frame_rotated)
                            cv2.waitKey(1)
                        except Exception as e:
                            print(f"[HDMI ERROR] imshow fallito: {e}")

                ok1, buf1 = cv2.imencode(".jpg", display_canvas, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok1:
                    self.latest_cmos_jpeg = buf1.tobytes()

                jdb_preview = cv2.resize(jdb_frame, (jdb_frame.shape[1] // 1, jdb_frame.shape[0] // 1))
                ok2, buf2 = cv2.imencode(".jpg", jdb_preview, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok2:
                    self.latest_jdb_jpeg = buf2.tobytes()

            time.sleep(1 / 30.0)

    def status_dict(self):
        with self.lock:
            return {

                "mode": self.mode_name,
                "phantom": bool(self.phantom_mode),
                "cam_w": int(self.cam_w),
                "cam_h": int(self.cam_h),
                "magnification": round(float(self.optics.magnification), 3),
                "pitch_x": round(float(self.optics.pitch_x_um), 2),
                "pitch_y": round(float(self.optics.pitch_y_um), 2),
                "fiber_core_um": float(self.optics.fiber_core_um),
                "l1": float(self.optics.focal_length_l1_mm),
                "l2": float(self.optics.focal_length_l2_mm),
                "pixels_inside_fiber": int(self.max_fiber_pixels),
                "total_pixels": int(self.optics.jdb_w_px * self.optics.jdb_h_px),
                "fiber_pct": round(float(self.fiber_pct), 1),
                "calibrated": bool(self.calibrated),
                "target_px": int(self.target_microled_pixels),
                "freq_hz": float(self.freq_hz),
                "duty_pct": float(self.duty_cycle_pct),
                "is_stimulating": bool(self.is_stimulating),
                "current_cmos_radius": int(getattr(self, "current_cmos_radius", 12)),
                "shutter_status": getattr(self, "shutter_status", "Blue only"),
                "neurons": int(len(self.selected_rois)),
                "active_led_pixels": int(getattr(self, "active_led_pixels", 0)),
                "output_mode": self.output_mode,
                "zoom_scale": round(float(self.zoom_scale), 2),
                "frozen": bool(getattr(self, "frozen", False)),
                "manual_radius": int(getattr(self, "manual_radius", self.current_cmos_radius)),
                "cam_index_used": int(getattr(self, "cam_index_used", -1)),
                "cam_resolution_match": bool(getattr(self, "cam_resolution_match", False)),
                "hdmi_window_open": bool(self._hdmi_window_open),
            }


system = MiniscopeSystem()


# ============================================================
#  ROUTES
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")


def _mjpeg_generator(getter):
    while True:
        frame = getter()
        if frame is not None:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(1 / 30.0)


@app.route("/video_feed")
def video_feed():
    return Response(_mjpeg_generator(lambda: system.latest_cmos_jpeg),
                     mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/jdb_feed")
def jdb_feed():
    return Response(_mjpeg_generator(lambda: system.latest_jdb_jpeg),
                     mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/status")
def status():
    return jsonify(system.status_dict())


@app.route("/api/set_lenses", methods=["POST"])
def set_lenses():
    data = request.get_json()
    system.set_lenses(float(data["l1"]), float(data["l2"]))
    return jsonify(system.status_dict())


@app.route("/api/set_fiber", methods=["POST"])
def set_fiber():
    data = request.get_json()
    system.set_fiber_core(float(data["fiber_um"]))
    return jsonify(system.status_dict())


@app.route("/api/set_target_px", methods=["POST"])
def set_target_px():
    data = request.get_json()
    system.set_target_pixels(int(data["value"]))
    return jsonify(system.status_dict())


@app.route("/api/set_freq", methods=["POST"])
def set_freq():
    data = request.get_json()
    system.set_frequency(float(data["value"]))
    return jsonify(system.status_dict())


@app.route("/api/set_duty", methods=["POST"])
def set_duty():
    data = request.get_json()
    system.set_duty_cycle(float(data["value"]))
    return jsonify(system.status_dict())


@app.route("/api/toggle_stim", methods=["POST"])
def toggle_stim():
    system.toggle_stimulation()
    return jsonify(system.status_dict())


@app.route("/api/clear_rois", methods=["POST"])
def clear_rois():
    system.clear_rois()
    return jsonify(system.status_dict())


@app.route("/api/add_roi", methods=["POST"])
def add_roi():
    data = request.get_json()
    system.add_roi(float(data["x"]), float(data["y"]))
    return jsonify(system.status_dict())


@app.route("/api/remove_last_roi", methods=["POST"])
def remove_last_roi():
    system.remove_last_roi()
    return jsonify(system.status_dict())


@app.route("/api/add_roi_drag", methods=["POST"])
def add_roi_drag():
    data = request.get_json()
    system.add_roi_drag(float(data["x1"]), float(data["y1"]), float(data["x2"]), float(data["y2"]))
    return jsonify(system.status_dict())


@app.route("/api/bump_radius", methods=["POST"])
def bump_radius():
    data = request.get_json()
    system.bump_manual_radius(int(data["delta"]))
    return jsonify(system.status_dict())


@app.route("/api/toggle_freeze", methods=["POST"])
def toggle_freeze():
    system.toggle_freeze()
    return jsonify(system.status_dict())


@app.route("/api/calibrate", methods=["POST"])
def calibrate():
    success = system.run_calibration()
    result = system.status_dict()
    result["calibration_success"] = success
    return jsonify(result)


@app.route("/api/reset_zoom", methods=["POST"])
def reset_zoom():
    system.reset_zoom()
    return jsonify(system.status_dict())


@app.route("/api/zoom", methods=["POST"])
def zoom():
    data = request.get_json()
    system.apply_zoom(float(data["delta"]), float(data["x"]), float(data["y"]))
    return jsonify(system.status_dict())


@app.route("/api/pan", methods=["POST"])
def pan():
    data = request.get_json()
    system.pan(float(data["dx"]), float(data["dy"]))
    return jsonify(system.status_dict())


@app.route("/api/set_output", methods=["POST"])
def set_output():
    data = request.get_json()
    system.set_output_mode(data["mode"])
    return jsonify(system.status_dict())


@app.route("/api/set_camera_mode", methods=["POST"])
def set_camera_mode():
    data = request.get_json()
    system.set_camera_mode(data["mode"])
    return jsonify(system.status_dict())

@app.route("/api/monitors")
def monitors():
    try:
        from screeninfo import get_monitors
        mons = get_monitors()
        return jsonify({
            "ok": True,
            "count": len(mons),
            "monitors": [
                {"index": i, "width": m.width, "height": m.height, "x": m.x, "y": m.y, "primary": m.is_primary}
                for i, m in enumerate(mons)
            ],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
