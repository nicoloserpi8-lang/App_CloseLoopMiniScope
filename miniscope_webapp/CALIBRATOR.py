import time
import cv2
import numpy as np
from OPTICS_CONFIG import OpticsConfig

# Variables for manual calibration backup
manual_points = []


def mouse_calibration_click(event, x, y, flags, param):
    """Mouse callback to manually click 4 calibration points if automatic detection fails."""
    global manual_points
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(manual_points) < 4:
            manual_points.append((x, y))
            print(
                f"[MANUAL CALIB] Point {len(manual_points)}/4 set at: ({x}, {y})"
            )


def print_cli_help():
    """Prints terminal help instructions for the calibrator module."""
    print("\n" + "=" * 60)
    print("         DUAL MICROLED CALIBRATOR - KEYBOARD CONTROLS")
    print("=" * 60)
    print("  [SPACE]    : Run 4-Point Automatic Calibration Routine")
    print("  [m]        : Toggle Manual Point Click Mode (4 clicks)")
    print("  [r]        : Reset Manual Calibration Points")
    print("  [t]        : Toggle Blue / Red Pattern Display")
    print("  [h]        : Print this Help Menu")
    print("  [q]        : Quit Standalone Calibrator")
    print("=" * 60 + "\n")


def select_execution_mode():
    """Prompts user to select operating mode for standalone calibrator test."""
    print("\n" + "=" * 60)
    print("         MICROLED HOMOGRAPHY CALIBRATOR - INITIALIZATION")
    print("=" * 60)
    print("Select target hardware mode:")
    print("  [1] PC TEST MODE        -> Uses PC Webcam (640x480)")
    print("  [2] MINISCOPE RIG MODE  -> Uses Miniscope V4 Sensor (608x608)")
    print("=" * 60)

    while True:
        choice = input("Enter choice (1 or 2): ").strip()
        if choice == "1":
            print("\n[CONFIG] Loaded PC TEST MODE (640x480)")
            return "PC", 640, 480
        elif choice == "2":
            print("\n[CONFIG] Loaded MINISCOPE RIG MODE (608x608)")
            return "RIG", 608, 608
        else:
            print("Invalid input. Please enter 1 or 2.")


class DualMicroLEDCalibrator:
    """Calculates perspective homography matrices between Miniscope CMOS sensor

    and MicroLED projection array using active 4-dot optical calibration patterns.
    """

    def __init__(self, optics_config):
        self.optics = optics_config
        self.jdb_w = optics_config.jdb_w_px
        self.jdb_h = optics_config.jdb_h_px
        self.center = (self.jdb_w // 2, self.jdb_h // 2)

    def generate_calibration_pattern(self, channel="blue"):
        """Generates a 4-point calibration matrix aligned with optical fiber margins."""
        pattern = np.zeros((self.jdb_h, self.jdb_w, 3), dtype=np.uint8)

        r_fiber_um = (
            self.optics.fiber_core_um / 2.0
        ) / self.optics.magnification
        rx_px = r_fiber_um / self.optics.pitch_x_um
        ry_px = r_fiber_um / self.optics.pitch_y_um

        margin_x = int(rx_px * 0.45)
        margin_y = int(ry_px * 0.45)

        points = [
            (self.center[0] - margin_x, self.center[1] - margin_y),
            (self.center[0] + margin_x, self.center[1] - margin_y),
            (self.center[0] + margin_x, self.center[1] + margin_y),
            (self.center[0] - margin_x, self.center[1] + margin_y),
        ]

        color = (255, 0, 0) if channel == "blue" else (0, 0, 255)
        dot_radius = max(6, int(18 / self.optics.magnification))

        for pt in points:
            cv2.circle(pattern, pt, dot_radius, color, -1)

        return pattern, np.float32(points)

    def detect_cam_points(self, frame, threshold_val=100):
        """Detects bright calibration spot centroids on camera frame."""
        if len(frame.shape) == 3:
            # I puntini di calibrazione sono blu puri: usiamo direttamente il
            # canale blu invece della luminanza in scala di grigi, che li
            # renderebbe quasi invisibili (il blu pesa solo ~11% nella luminanza).
            gray = frame[:, :, 0]
        else:
            gray = frame
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        _, thresh = cv2.threshold(
            blurred, threshold_val, 255, cv2.THRESH_BINARY
        )

        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        print(f"[CALIB DEBUG] Contorni totali trovati: {len(contours)}")
        areas = [cv2.contourArea(c) for c in contours]
        print(f"[CALIB DEBUG] Aree dei contorni: {sorted(areas, reverse=True)[:10]}")
        print(f"[CALIB DEBUG] Valore massimo canale blu nel frame: {gray.max()}, soglia usata: {threshold_val}")
        cv2.imwrite("debug_calib_frame.jpg", frame)
        cv2.imwrite("debug_calib_thresh.jpg", thresh)

        centers = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 10 < area < 10000:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    centers.append((cX, cY))

        if len(centers) == 4:
            # Sort top to bottom, then left to right
            centers = sorted(centers, key=lambda p: p[1])
            top_pts = sorted(centers[:2], key=lambda p: p[0])
            bot_pts = sorted(centers[2:], key=lambda p: p[0], reverse=True)
            return np.float32([top_pts[0], top_pts[1], bot_pts[0], bot_pts[1]])

        return None

    def run_full_calibration(self, cap, jdb_win_name="MICROLED_DISPLAY"):
        """Runs automated 4-point homography calibration procedure."""
        print(
            "\n[CALIBRATION] Starting automatic calibration pattern projection..."
        )

        pattern_blue, pts_led_blue = self.generate_calibration_pattern("blue")
        cv2.imshow(jdb_win_name, pattern_blue)
        cv2.waitKey(600)

        ret, frame_blue = cap.read()
        if not ret or frame_blue is None:
            print("[CALIBRATION ERROR] Failed to capture frame from camera.")
            return None, None, False

        pts_cam_blue = self.detect_cam_points(frame_blue)

        if pts_cam_blue is not None:
            print("[CALIBRATION] ✅ 4 Dots detected automatically on CMOS!")
            M_cam2led = cv2.getPerspectiveTransform(pts_cam_blue, pts_led_blue)
            M_led2cam = cv2.getPerspectiveTransform(pts_led_blue, pts_cam_blue)
            return M_cam2led, M_led2cam, True
        else:
            print(
                "[WARN] Automatic 4-point detection failed. Falling back to default proportional matrix."
            )
            cam_h, cam_w = frame_blue.shape[:2]

            pts_cam_default = np.float32(
                [
                    [int(cam_w * 0.35), int(cam_h * 0.35)],
                    [int(cam_w * 0.65), int(cam_h * 0.35)],
                    [int(cam_w * 0.65), int(cam_h * 0.65)],
                    [int(cam_w * 0.35), int(cam_h * 0.65)],
                ]
            )
            M_cam2led = cv2.getPerspectiveTransform(
                pts_cam_default, pts_led_blue
            )
            M_led2cam = cv2.getPerspectiveTransform(
                pts_led_blue, pts_cam_default
            )
            return M_cam2led, M_led2cam, False


RapidCalibrator = DualMicroLEDCalibrator

# --- STANDALONE TEST CLI ---
if __name__ == "__main__":
    mode_name, target_w, target_h = select_execution_mode()
    optics = OpticsConfig()
    calib = DualMicroLEDCalibrator(optics)

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)

    win_name = f"Calibrator CMOS Preview [{mode_name} MODE]"
    jdb_win = "MICROLED_PATTERN_TEST"

    cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE)
    cv2.namedWindow(jdb_win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win_name, mouse_calibration_click)

    current_channel = "blue"
    pattern, pts_led = calib.generate_calibration_pattern(current_channel)

    print_cli_help()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            frame = np.full((target_h, target_w, 3), 40, dtype=np.uint8)

        canvas = frame.copy()
        cv2.imshow(jdb_win, pattern)

        for idx, pt in enumerate(manual_points):
            cv2.circle(canvas, pt, 5, (0, 255, 0), -1)
            cv2.putText(
                canvas,
                f"P{idx + 1}",
                (pt[0] + 8, pt[1] - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )

        if len(manual_points) == 4:
            pts_cam_manual = np.float32(manual_points)
            M_cam2led = cv2.getPerspectiveTransform(
                pts_cam_manual, pts_led
            )
            cv2.putText(
                canvas,
                "MANUAL HOMOGRAPHY READY",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )

        cv2.imshow(win_name, canvas)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        elif key == ord(" "):
            M_cam2led, M_led2cam, success = calib.run_full_calibration(
                cap, jdb_win
            )
            print(
                f"[CALIBRATION RESULT] Homography matrix computed: {success}"
            )
        elif key == ord("t"):
            current_channel = "red" if current_channel == "blue" else "blue"
            pattern, pts_led = calib.generate_calibration_pattern(
                current_channel
            )
            print(f"[PATTERN] Switched channel to {current_channel.upper()}")
        elif key == ord("r"):
            manual_points.clear()
            print("[MANUAL CALIB] Points cleared.")
        elif key == ord("h"):
            print_cli_help()

    cap.release()
    cv2.destroyAllWindows()
