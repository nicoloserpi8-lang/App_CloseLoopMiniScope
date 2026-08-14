import cv2
import numpy as np

# 1. Coordinate note proiettate dal MicroLED (stesso margine usato nello Script 1)
WIDTH_LED, HEIGHT_LED = 380, 500
MARGIN = 40

PTS_MICROLED = np.float32([
    [MARGIN, MARGIN],                       # Top-Left
    [WIDTH_LED - MARGIN, MARGIN],           # Top-Right
    [MARGIN, HEIGHT_LED - MARGIN],          # Bottom-Left
    [WIDTH_LED - MARGIN, HEIGHT_LED - MARGIN] # Bottom-Right
])

def calcola_calibrazione(img_sfondo, img_con_pattern, min_thresh=40):
    """
    Sottrae lo sfondo, individua i 4 punti e calcola la matrice di trasformazione.
    """
    # Converti in scala di grigi
    gray_sfondo = cv2.cvtColor(img_sfondo, cv2.COLOR_BGR2GRAY) if len(img_sfondo.shape) == 3 else img_sfondo
    gray_pattern = cv2.cvtColor(img_con_pattern, cv2.COLOR_BGR2GRAY) if len(img_con_pattern.shape) == 3 else img_con_pattern

    # SOTTRAZIONE SFONDO: Elimina il campione (pollini)
    diff = cv2.subtract(gray_pattern, gray_sfondo)

    # Thresholding per isolare solo i punti luminosi
    _, mask = cv2.threshold(diff, min_thresh, 255, cv2.THRESH_BINARY)

    # Trova i contorni
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    punti_cmos = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 5 < area < 2000:  # Filtro dimensioni punto
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = float(M["m10"] / M["m00"])
                cy = float(M["m01"] / M["m00"])
                punti_cmos.append([cx, cy])

    if len(punti_cmos) != 4:
        print(f"❌ ERRORE: Trovati {len(punti_cmos)} punti invece di 4!")
        print("Consiglio: Regola 'min_thresh' o aumenta la luminosità del MicroLED.")
        return None, diff

    # Ordina i punti trovati nello stesso ordine: [TL, TR, BL, BR]
    punti_cmos = np.array(punti_cmos, dtype=np.float32)
    punti_cmos_ordinati = ordina_punti(punti_cmos)

    # Calcola la matrice di Trasformazione (Homography)
    # M mappa le coordinate (X_cmos, Y_cmos) -> (X_microled, Y_microled)
    H_matrix, _ = cv2.findHomography(punti_cmos_ordinati, PTS_MICROLED)

    print("✅ Calibrazione riuscita con successo!")
    return H_matrix, diff

def ordina_punti(pts):
    """Ordina 4 punti nello schema: Top-Left, Top-Right, Bottom-Left, Bottom-Right."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)] # Top-Left
    rect[3] = pts[np.argmax(s)] # Bottom-Right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] # Top-Right
    rect[2] = pts[np.argmax(diff)] # Bottom-Left
    return rect


# --- PROCEDURA DI ESECUZIONE ---
if __name__ == "__main__":
    # Esempio usando la web-camera / CMOS del Miniscope (cam index 0 o 1)
    cap = cv2.VideoCapture(0)

    print("\n--- PROCEDURA DI CALIBRAZIONE ---")
    print("1. Assicurati che il MicroLED sia SPENTO (Schermo Nero).")
    input("Premi INVIO per acquisire lo SFONDO (Campione Pollini)... ")
    ret, frame_sfondo = cap.read()

    print("\n2. Ora avvia lo Script 1 per proiettare il pattern di calibrazione sul MicroLED.")
    input("Premi INVIO per acquisire il frame con i PUNTI ACCESI... ")
    ret, frame_pattern = cap.read()

    # Calcola la matrice
    H_matrix, img_pulita = calcola_calibrazione(frame_sfondo, frame_pattern)

    if H_matrix is not None:
        # Salva la matrice di calibrazione su file per usarla nell'app principale
        np.save("matrice_calibrazione_microled.npy", H_matrix)
        print("\nMatrice salvata in 'matrice_calibrazione_microled.npy'!")

    # Mostra l'immagine pulita dalla sottrazione
    cv2.imshow("Sottrazione Sfondo (Solo Punti)", img_pulita)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    cap.release()