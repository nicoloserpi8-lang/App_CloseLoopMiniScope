# NPN Miniscope — Web Control Interface

Interfaccia web locale per il sistema di controllo closed-loop Miniscope + MicroLED,
costruita sopra i tuoi moduli originali **senza modificarne la logica**:

- `OPTICS_CONFIG.py` — invariato
- `SHUTTER_CONTROL.py` — invariato
- `CALIBRATOR.py` — invariato
- `HARDWARE_UTILS.py` — invariato
- `app.py` — nuovo backend Flask che riusa questi moduli combinando la logica
  di **`main.py`** (closed-loop, stimolazione, calibrazione, raggio automatico)
  e quella di **`ROI_Microled_selector.py`** (raggio ROI manuale via drag,
  freeze frame, regolazione raggio +/-) in un'unica interfaccia

## Installazione

```bash
cd miniscope_webapp
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

## Avvio

```bash
python app.py
```

Poi apri il browser su **http://127.0.0.1:5000**

Se non trova nessuna camera (es. stai testando su un altro PC), parte
automaticamente in **modalità phantom**: genera un'immagine sintetica con
"neuroni" luminosi finti, così puoi comunque testare l'interfaccia — proprio
come vedi nello screenshot di riferimento.

## Cosa fa ogni parte dell'interfaccia

### Pannello "Optics & calibration"
- **Lens L1 / L2 (mm)** → equivalenti ai comandi `[l]` del vecchio `main.py`
- **Fibre core (µm)** → equivalente al comando `[o]`
- Magnification, MicroLED pitch, Pixels inside fibre si aggiornano in automatico
- **Calibrate** → esegue `DualMicroLEDCalibrator.run_full_calibration()`
  (equivalente al comando `[c]`)

### Pannello "Stimulation"
- **MicroLED px / neuron** → equivalente al comando `[p]`
- **Frequency (Hz)** → equivalente al comando `[f]`
- **Duty cycle (%)** → equivalente al comando `[d]`
- **Start/Stop stimulation** → equivalente al comando `[s]`
- **Clear neurons** → equivalente al comando `[r]`

### Pannello "MicroLED"
- Anteprima live del pattern proiettato (blu = riposo, rosso = stimolazione attiva)
- **Output**: `Virtual (no projector)` mostra solo l'anteprima nel browser;
  `Hardware (HDMI window)` apre davvero la finestra `cv2` a schermo intero
  sul secondo monitor, esattamente come faceva `main.py`

### Video CMOS (pannello centrale)
- **Click semplice** (senza trascinare) → aggiunge una ROI con **raggio automatico**,
  calcolato dall'omografia in base a "MicroLED px / neuron" — equivalente al click
  sinistro di `main.py`
- **Trascina (click + drag)** → aggiunge una ROI con **raggio manuale**, pari alla
  distanza di trascinamento — equivalente al comportamento di `ROI_Microled_selector.py`
- **Raggio + / Raggio −** (barra in basso) → equivalenti ai tasti `[+]`/`[-]` di
  `ROI_Microled_selector.py`, regolano il raggio di default usato dal prossimo trascinamento
- **Freeze / Unfreeze** (barra in basso, o barra spaziatrice) → equivalente al tasto
  `[SPACE]` di `ROI_Microled_selector.py`, congela il frame per selezionare ROI con calma
- **Click destro** → rimuove l'ultima ROI aggiunta
- **Rotellina del mouse** → zoom in/out centrato sul cursore
- **Shift + trascina** (o click centrale + trascina) → pan
- **Reset zoom** (barra in basso) → riporta lo zoom a 1x

## Note

- Il controller degli shutter resta in `dummy_mode=True` di default (come nello
  script originale). Per usare l'hardware reale, basta cambiare
  `ShutterController(port="COM3", dummy_mode=True)` in `app.py` con la porta
  seriale corretta e `dummy_mode=False`.
- La modalità camera (PC 640x480 / RIG 608x608) è impostata di default su `PC`
  in `MiniscopeSystem.__init__`. Se vuoi esporla anche in UI con un selettore
  dedicato, l'endpoint `/api/set_camera_mode` è già pronto lato backend: basta
  aggiungere un `<select>` nell'HTML che lo richiama.
