import time
import serial


class ShutterController:
    """Controls physical optical shutters (or microcontrollers like Arduino/Teensy)

    via serial interface with fallback to simulation mode for PC testing.
    """

    def __init__(self, port="COM3", baudrate=9600, dummy_mode=True):
        self.port = port
        self.baudrate = baudrate
        self.dummy_mode = dummy_mode
        self.ser = None

        self.connect()

    def connect(self, port=None):
        """Attempts connection to the serial device or defaults to dummy mode."""
        if port:
            self.port = port

        if not self.dummy_mode:
            try:
                self.ser = serial.Serial(
                    self.port, self.baudrate, timeout=0.1
                )
                time.sleep(1)
                print(f"[SHUTTER] Connected successfully on {self.port}")
            except Exception as e:
                print(
                    f"[WARN] Connection to {self.port} failed: {e}. Running in DUMMY mode."
                )
                self.dummy_mode = True
        else:
            print(
                f"[SHUTTER] Initialized in DUMMY MODE (Virtual Shutter active)."
            )

    def toggle_dummy_mode(self):
        """Toggles between Hardware Mode and PC Test (Dummy) Mode."""
        self.dummy_mode = not self.dummy_mode
        state = "DUMMY MODE (PC Test)" if self.dummy_mode else "HARDWARE MODE"
        print(f"[SHUTTER] Switched to {state}")
        if not self.dummy_mode and (self.ser is None or not self.ser.is_open):
            self.connect()

    def set_blue_only(self):
        if self.dummy_mode:
            return
        try:
            self.ser.write(b"B\n")
        except Exception as e:
            print(f"[SHUTTER ERROR] Failed to send 'BLUE' command: {e}")

    def set_red_only(self):
        if self.dummy_mode:
            return
        try:
            self.ser.write(b"R\n")
        except Exception as e:
            print(f"[SHUTTER ERROR] Failed to send 'RED' command: {e}")

    def set_both_on(self):
        if self.dummy_mode:
            return
        try:
            self.ser.write(b"B\n")
            self.ser.write(b"R\n")
        except Exception as e:
            print(f"[SHUTTER ERROR] Failed to send 'BOTH' command: {e}")

    def close_all(self):
        if self.dummy_mode:
            return
        try:
            self.ser.write(b"0\n")
        except Exception as e:
            print(f"[SHUTTER ERROR] Failed to send 'CLOSE ALL' command: {e}")

    def start_interleaved_pulsing(self, freq_hz, duty_cycle_pct):
        if self.dummy_mode:
            print(
                f"[SHUTTER DUMMY PULSE] Active at {freq_hz:.1f} Hz @ {duty_cycle_pct:.0f}% Duty Cycle"
            )
            return
        try:
            cmd = f"PULSE,{freq_hz:.2f},{duty_cycle_pct:.1f}\n".encode()
            self.ser.write(cmd)
        except Exception as e:
            print(f"[SHUTTER ERROR] Failed to send 'PULSE' command: {e}")

    def close(self):
        if self.ser and self.ser.is_open:
            try:
                self.close_all()
                self.ser.close()
                print("[SHUTTER] Serial connection closed.")
            except Exception as e:
                print(f"[SHUTTER ERROR] Error closing serial port: {e}")


def print_cli_help():
    """Terminal guide for testing Shutter Controller stand-alone."""
    print("\n" + "=" * 60)
    print("             SHUTTER CONTROLLER - TERMINAL TEST MENU")
    print("=" * 60)
    print("Commands:")
    print("  [1] Set Blue Shutter ONLY")
    print("  [2] Set Red Shutter ONLY")
    print("  [3] Set BOTH Shutters ON")
    print("  [0] CLOSE ALL Shutters")
    print("  [p] Send Interleaved Pulse Command")
    print("  [t] Toggle DUMMY / HARDWARE Mode")
    print("  [c] Change COM Port")
    print("  [h] Print this Help Menu")
    print("  [q] Quit Standalone Test")
    print("=" * 60 + "\n")


# --- STANDALONE TESTING CLI ---
if __name__ == "__main__":
    print("[TEST MODE] Launching Shutter Controller interactive CLI...")
    shutter = ShutterController(port="COM3", dummy_mode=True)
    print_cli_help()

    while True:
        cmd = input("Enter shutter command ([h] for help): ").strip().lower()

        if cmd == "1":
            shutter.set_blue_only()
            print("-> Command: Blue ON")
        elif cmd == "2":
            shutter.set_red_only()
            print("-> Command: Red ON")
        elif cmd == "3":
            shutter.set_both_on()
            print("-> Command: Both ON")
        elif cmd == "0":
            shutter.close_all()
            print("-> Command: Close All")
        elif cmd == "p":
            f = float(input("Enter Frequency (Hz) [default 10]: ") or 10)
            d = float(input("Enter Duty Cycle (%) [default 20]: ") or 20)
            shutter.start_interleaved_pulsing(f, d)
        elif cmd == "t":
            shutter.toggle_dummy_mode()
        elif cmd == "c":
            new_port = input("Enter new COM port (e.g. COM4, COM5): ").strip()
            shutter.dummy_mode = False
            shutter.connect(new_port)
        elif cmd == "h":
            print_cli_help()
        elif cmd == "q":
            shutter.close()
            print("Exiting shutter test.")
            break
        else:
            print("Unknown command. Type 'h' for help.")
