import cv2
import numpy as np
import screeninfo


def genera_pattern_calibrazione_ottimizzato(width=380, height=500, margin_x=70, margin_y=80):
    """
    Crea il pattern 380x500 ma posiziona i 4 punti all'interno del campo
    visivo effettivo della fibra (tenendo conto della magnificazione 1.1x).
    """
    pattern = np.zeros((height, width, 3), dtype=np.uint8)

    # Coordinate dei 4 punti portate dentro il diametro visibile della fibra
    pts_microled = [
        (margin_x, margin_y),  # Top-Left
        (width - margin_x, margin_y),  # Top-Right
        (margin_x, height - margin_y),  # Bottom-Left
        (width - margin_x, height - margin_y)  # Bottom-Right
    ]

    # Disegna i 4 punti di calibrazione (Cerchio centrale con croce ad alta visibilità)
    for i, pt in enumerate(pts_microled):
        # Punto bianco pieno (Luminosità max)
        cv2.circle(pattern, pt, 10, (255, 255, 255), -1)
        # Marker interno a croce per definire il centroide esatto
        cv2.drawMarker(pattern, pt, (0, 0, 255), cv2.MARKER_CROSS, 20, 2)

    # Disegna un'ellisse/cerchio guida che simula l'ingresso della fibra ottica
    center = (width // 2, height // 2)
    axes = (int((width // 2) - 15), int((height // 2) - 15))
    cv2.ellipse(pattern, center, axes, 0, 0, 360, (100, 100, 100), 1)

    return pattern, np.float32(pts_microled)


def proietta():
    WIDTH, HEIGHT = 380, 500

    # Genera il pattern adattato alla fibra
    pattern, pts_target = genera_pattern_calibrazione_ottimizzato(WIDTH, HEIGHT)

    # Rilevamento automatico dello Schermo 2
    monitors = screeninfo.get_monitors()
    offset_x = monitors[1].x if len(monitors) > 1 else 1920
    offset_y = monitors[1].y if len(monitors) > 1 else 0

    win_name = "Calibrazione_MicroLED_Fibra"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(win_name, offset_x, offset_y)
    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    print("--- PROIEZIONE PATTERN (ADATTATO A FIBRA 1.1x) ---")
    print(f"Coordinate MicroLED utilizzate per la calibrazione:\n{pts_target}")
    print("\nPremi 'Q' per chiudere la proiezione.")

    while True:
        cv2.imshow(win_name, pattern)
        if cv2.waitKey(100) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    proietta()