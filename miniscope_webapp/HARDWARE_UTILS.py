import time
import cv2
from screeninfo import get_monitors


def find_miniscope_cam_index_smart(max_indices=6, mode="PC"):
    """Scans DirectShow ports to identify either standard PC webcam (640x480)

    or native Miniscope V4 sensor (608x608) based on mode.
    """
    mode = mode.upper()
    target_w, target_h = (608, 608) if mode == "RIG" else (640, 480)

    print(
        f"\n[HARDWARE] Searching for camera via DirectShow (Target: {mode} Mode - {target_w}x{target_h})..."
    )

    for idx in range(max_indices):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)

            time.sleep(0.15)  # Driver settling time for USB / Cypress FX3
            ret, frame = cap.read()

            if ret and frame is not None:
                h, w = frame.shape[:2]
                print(f"  -> Port [{idx}]: Detected Resolution = {w}x{h}")

                if w == target_w and h == target_h:
                    print(
                        f"✅ [OK] Suitable Camera confirmed at INDEX: {idx} ({w}x{h})\n"
                    )
                    cap.release()
                    return idx
            cap.release()

    print(
        f"⚠️ [WARNING] No native {target_w}x{target_h} camera auto-detected. Defaulting to Index 0."
    )
    return 0


def find_miniscope_cam_index(mode="PC"):
    """Compatibility alias for smart search function."""
    return find_miniscope_cam_index_smart(mode=mode)


def get_jdb_monitor_coords(jdb_monitor_index=1):
    """Detects multi-monitor setups and returns coordinates for MicroLED HDMI display."""
    try:
        monitors = get_monitors()
        print(f"\n[HARDWARE] System monitors detected ({len(monitors)}):")
        for idx, m in enumerate(monitors):
            print(
                f"  - Monitor [{idx}]: {m.width}x{m.height} at X={m.x}, Y={m.y} {'(Primary)' if m.is_primary else ''}"
            )

        if len(monitors) > jdb_monitor_index:
            m = monitors[jdb_monitor_index]
            print(
                f"[HARDWARE] Selected Monitor [{jdb_monitor_index}] for MicroLED: {m.width}x{m.height} at X={m.x}, Y={m.y}\n"
            )
            return m.x, m.y, m.width, m.height
        else:
            print(
                f"[WARN] Secondary monitor not found. Defaulting to primary monitor bounds (X=0, Y=0)."
            )
            m = monitors[0]
            return 0, 0, m.width, m.height

    except Exception as e:
        print(
            f"[WARN] screeninfo query failed ({e}). Forcing default fallback offset X=1920 px."
        )
        return 1920, 0, 380, 500


# --- STANDALONE TEST CLI ---
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("         HARDWARE UTILITIES - STANDALONE DIAGNOSTICS")
    print("=" * 60)
    print("Select test mode:")
    print("  [1] TEST PC WEBCAM DISCOVERY (640x480)")
    print("  [2] TEST MINISCOPE V4 DISCOVERY (608x608)")
    print("=" * 60)

    choice = input("Enter choice (1 or 2): ").strip()
    test_mode = "RIG" if choice == "2" else "PC"

    cam_idx = find_miniscope_cam_index_smart(mode=test_mode)
    x, y, w, h = get_jdb_monitor_coords(jdb_monitor_index=1)

    print("\n--- DIAGNOSTIC SUMMARY ---")
    print(f" Target Camera Index : {cam_idx}")
    print(f" MicroLED Monitor Box: {w}x{h} at Offset ({x}, {y})")
    print("---------------------------\n")