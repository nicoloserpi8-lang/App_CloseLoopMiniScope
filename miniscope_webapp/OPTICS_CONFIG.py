import cv2
import numpy as np


class OpticsConfig:
    """Optical setup configuration for the Miniscope V4 system coupled with

    the JDB MicroLED display matrix.
    """

    def __init__(
        self,
        f_l1_mm=50,
        f_l2_mm=30,
        fiber_core_um=1500.0,
        custom_magnification=None,
        mode="PC",
    ):
        # 1. REAL JDB MICROLED DISPLAY PARAMETERS
        self.jdb_w_px = 380  # Horizontal pixels
        self.jdb_h_px = 500  # Vertical pixels
        self.active_w_mm = 1.600  # Active horizontal dimension in mm
        self.active_h_mm = 2.048  # Active vertical dimension in mm

        # 2. OPTICAL SYSTEM (FOCAL LENGTHS AND MAGNIFICATION)
        self.focal_length_l1_mm = float(f_l1_mm)  # Lens 1 Focal Length (mm)
        self.focal_length_l2_mm = float(f_l2_mm)  # Lens 2 Focal Length (mm)
        self.fiber_core_um = float(fiber_core_um)  # Fiber core diameter (um)
        self.custom_magnification = custom_magnification

        # 3. OPTICAL FIBER & SENSOR RESOLUTION
        self.cam_pixel_size_um = (
            4.8  # Miniscope CMOS Sensor Pixel Pitch (um)
        )

        self.set_mode(mode)

    def set_mode(self, mode="PC"):
        """Dynamically adjusts camera dimensions based on hardware mode."""
        self.mode = mode.upper()
        if self.mode == "RIG":
            self.cam_w_px = 608  # Native Miniscope V4 CMOS resolution
            self.cam_h_px = 608
        else:
            self.mode = "PC"
            self.cam_w_px = 640  # Standard PC Webcam resolution
            self.cam_h_px = 480

    @property
    def pitch_x_um(self):
        """Calculates horizontal pixel pitch of the MicroLED matrix in um."""
        return (self.active_w_mm * 1000.0) / self.jdb_w_px

    @property
    def pitch_y_um(self):
        """Calculates vertical pixel pitch of the MicroLED matrix in um."""
        return (self.active_h_mm * 1000.0) / self.jdb_h_px

    @property
    def microled_pitch_um(self):
        """Calculates average MicroLED pixel pitch in um."""
        return (self.pitch_x_um + self.pitch_y_um) / 2.0

    @property
    def magnification(self):
        """Calculates or retrieves optical magnification (M = L2 / L1)."""
        if self.custom_magnification is not None:
            return float(self.custom_magnification)
        if self.focal_length_l1_mm <= 0:
            return 1.0
        return float(self.focal_length_l2_mm) / float(self.focal_length_l1_mm)

    @property
    def fiber_radius_px_on_jdb(self):
        """Calculates equivalent fiber core radius in MicroLED display pixels."""
        r_fiber_on_display_um = (
            self.fiber_core_um / 2.0
        ) / self.magnification
        rx_px = int(r_fiber_on_display_um / self.pitch_x_um)
        ry_px = int(r_fiber_on_display_um / self.pitch_y_um)
        return int((rx_px + ry_px) / 2.0)

    def get_valid_fiber_mask(self):
        """Generates a binary ellipse mask corresponding to the fiber optics boundary."""
        mask = np.zeros((self.jdb_h_px, self.jdb_w_px), dtype=np.uint8)
        center = (self.jdb_w_px // 2, self.jdb_h_px // 2)

        r_fiber_on_display_um = (
            self.fiber_core_um / 2.0
        ) / self.magnification
        rx_px = int(r_fiber_on_display_um / self.pitch_x_um)
        ry_px = int(r_fiber_on_display_um / self.pitch_y_um)

        cv2.ellipse(mask, center, (rx_px, ry_px), 0, 0, 360, 255, -1)

        pixels_inside = np.count_nonzero(mask)
        total_pixels = self.jdb_w_px * self.jdb_h_px
        percent = (pixels_inside / total_pixels) * 100

        return mask, pixels_inside, percent

    def update_lenses(self, f_l1_mm, f_l2_mm):
        """Updates lens focal lengths and recalculates optical magnification."""
        self.focal_length_l1_mm = float(f_l1_mm)
        self.focal_length_l2_mm = float(f_l2_mm)
        self.custom_magnification = None  # Reset manual magnification override
        print(
            f"[OPTICS] Updated lenses: L1={self.focal_length_l1_mm}mm, L2={self.focal_length_l2_mm}mm | Mag = {self.magnification:.2f}x"
        )

    def update_magnification(self, mag):
        """Directly sets a custom magnification override value."""
        self.custom_magnification = float(mag)
        print(
            f"[OPTICS] Custom magnification set to: {self.magnification:.2f}x"
        )

    def update_fiber_core(self, core_um):
        """Updates optical fiber core diameter in micrometers."""
        self.fiber_core_um = float(core_um)
        print(
            f"[OPTICS] Fiber core diameter updated to: {self.fiber_core_um:.0f} um"
        )

    def print_summary(self):
        """Prints a comprehensive report of system optics to terminal."""
        _, inside, pct = self.get_valid_fiber_mask()
        print("\n================ REAL OPTICAL CONFIGURATION ================")
        print(f" Current Execution Mode: {self.mode}")
        print(
            f" MicroLED Active Area: {self.active_w_mm} mm x {self.active_h_mm} mm"
        )
        print(f" MicroLED Matrix: {self.jdb_w_px} x {self.jdb_h_px} px")
        print(
            f" CMOS Target Sensor: {self.cam_w_px} x {self.cam_h_px} px | Pitch: {self.cam_pixel_size_um} um"
        )
        print(
            f" Lens Focal Lengths: L1 = {self.focal_length_l1_mm} mm | L2 = {self.focal_length_l2_mm} mm"
        )
        print(
            f" Calculated Magnification (M = L2/L1): {self.magnification:.2f}x"
        )
        print(
            f" Calculated Pitch: X = {self.pitch_x_um:.2f} um | Y = {self.pitch_y_um:.2f} um"
        )
        print(f" Fiber Core Diameter: {self.fiber_core_um:.0f} um")
        print(
            f" MicroLED Pixels Inside Fiber: {inside} / {self.jdb_w_px * self.jdb_h_px} ({pct:.1f}%)"
        )
        print("=============================================================\n")


# --- STANDALONE TEST CLI ---
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("         OPTICS CONFIGURATION - STANDALONE TEST")
    print("=" * 60)
    print("Select test mode:")
    print("  [1] PC TEST MODE (640x480)")
    print("  [2] MINISCOPE RIG MODE (608x608)")
    print("=" * 60)

    choice = input("Enter choice (1 or 2): ").strip()
    mode = "RIG" if choice == "2" else "PC"

    optics = OpticsConfig(mode=mode)
    optics.print_summary()