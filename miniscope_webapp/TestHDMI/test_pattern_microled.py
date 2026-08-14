import cv2
import numpy as np
import screeninfo
import time


def crea_pattern_caratteristico(width, height, tick):
    # Crea uno sfondo nero (380x500)
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # 1. Bordo rettangolare bianco per testare i margini estremi del display
    cv2.rectangle(img, (0, 0), (width - 1, height - 1), (255, 255, 255), 2)

    # 2. Croce diagonale ad alto contrasto (Rosso e Verde)
    cv2.line(img, (0, 0), (width, height), (0, 0, 255), 2)  # Linea Rossa (BGR: 0, 0, 255)
    cv2.line(img, (width, 0), (0, height), (0, 255, 0), 2)  # Linea Verde (BGR: 0, 255, 0)

    # 3. Cerchi identificativi sui 4 Angoli (Raggio 25 px)
    cv2.circle(img, (40, 40), 25, (255, 0, 0), -1)  # In alto a SX: BLU
    cv2.circle(img, (width - 40, 40), 25, (0, 255, 0), -1)  # In alto a DX: VERDE
    cv2.circle(img, (40, height - 40), 25, (0, 0, 255), -1)  # In basso a SX: ROSSO
    cv2.circle(img, (width - 40, height - 40), 25, (0, 255, 255), -1)  # In basso a DX: GIALLO

    # 4. Cerchio Centrale Lampeggiante (Bianco) per confermare l'aggiornamento video
    if tick % 2 == 0:
        cv2.circle(img, (width // 2, height // 2), 40, (255, 255, 255), -1)

    # Scritta identificativa al centro
    cv2.putText(img, "380x500", (width // 2 - 45, height // 2 + 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    return img


def test_pattern_microled():
    WIDTH = 380
    HEIGHT = 500

    # Rileva la posizione dello Schermo 2
    monitori = screeninfo.get_monitors()

    if len(monitori) < 2:
        print("⚠️ Schermo 2 non rilevato automaticamente. Uso offset X = 1920.")
        offset_x = 1920
        offset_y = 0
    else:
        schermo2 = monitori[1]
        offset_x = schermo2.x
        offset_y = schermo2.y
        print(f"✅ Schermo 2 rilevato alle coordinate X={offset_x}, Y={offset_y}")

    win_name = "Test_Pattern_MicroLED"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(win_name, offset_x, offset_y)
    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    print("\n-----------------------------------------------------------")
    print(f"🎨 Pattern caratteristico ({WIDTH}x{HEIGHT} px) inviato allo Schermo 2!")
    print("Dovresti vedere una croce, 4 pallini ai bordi e un cerchio centrale LAMPEGGIANTE.")
    print("Premi 'Q' o 'ESC' per chiudere il test.")
    print("-----------------------------------------------------------\n")

    tick = 0
    while True:
        # Genera il frame con il pallino centrale che lampeggia ad ogni ciclo
        frame = crea_pattern_caratteristico(WIDTH, HEIGHT, tick)
        cv2.imshow(win_name, frame)

        # Attende 500 ms (il cerchio lampeggerà ogni mezzo secondo)
        key = cv2.waitKey(500) & 0xFF
        if key == ord('q') or key == ord('Q') or key == 27:
            break

        tick += 1

    cv2.destroyAllWindows()


if __name__ == "__main__":
    test_pattern_microled()