# PCB Vision

Local React + Python app for PCB defect inspection with a browser webcam and a custom Ultralytics YOLO detector.

## Start the app

Use Python 3.10 or newer. In the project directory, open two terminals:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

```powershell
npm install
npm run dev
```

If PowerShell blocks `npm.ps1`, use `npm.cmd install` and `npm.cmd run dev`. Open the URL shown by Vite, usually `http://localhost:5173`. The Vite dev server forwards `/api` requests to the Python service.

## Inspect with best.pt

The backend loads `best.pt` from the project root. All model classes are enabled, using the checkpoint's own names, boxes and confidence scores (minimum confidence 0.25). Health and Live inspection show the loaded classes and any model loading error.

The camera does not scan on its own: it captures a frame only when **Start conveyor** is pressed, after the board has been fed forward. Before detection, the backend finds the **green PCB** in the picture (OpenCV colour mask covering bright yellow-green to dark blue-green solder mask, largest green region of at least 4% of the frame and at least 25% truly green, so dark or grey surfaces are rejected), straightens it if it lies at an angle, crops to just the board and paints everything outside the board outline white. For the conveyor cycle, if only a sliver of board is visible at the frame edge (less than 15% of the frame), the result is "PCB only partly in view" and the conveyor stays stopped; a large board clipped by the frame edges is still inspected. Keep the whole board in view where possible: best.pt was trained on whole boards, and close-ups can miss defects. Uploads and two-side scans skip this rule, since photos are often cropped tight to the board. Defect boxes must lie at least 80% on the board, cover no more than 75% of the crop and must not run from one crop edge to the opposite edge; others are discarded as background or edge artifacts. Long defects such as cracks that run most of the board are kept. best.pt then runs only on that crop, at the image size it was trained with (read from the checkpoint), after boosting colour (×1.4) and contrast (×1.3) to make up for washed-out webcam frames, brightening dark boards (median brightness below 55 of 255, up to ×2) and with test-time augmentation (flipped and rescaled copies) for small, blurred crops. Boards reach the camera either way round, so the crop is inspected upright and turned 180° and the results are merged: a defect both orientations agree on is kept from 25% confidence, one found in only one orientation needs 50%. Boards lying sideways (90°) are not reliably detected by the current best.pt; so the belt and background cannot be mistaken for defects; boxes and the saved scan image refer to the crop. If no green board is in the picture, the model is not run and the result is "No green PCB in the frame"; the conveyor stays stopped. A manually selected region skips the green search. This applies to camera scans, uploads and both sides, so non-green boards (for example blue or black solder mask) need a manual region. No detections on the board means an unknown result; the conveyor stays stopped.

Training studio is optional and saves separate weights at `backend/data/model.pt`; it never overwrites the supplied `best.pt`. Dataset edits do not mark this external checkpoint stale. Replace the root `best.pt` to use another detector; it reloads when the file changes.

## Two-side inspection and PDF report

On **Live inspection**, switch between **One side** and **Two sides**. In two-side mode, capture or upload a front and a back image, then choose **Analyze both sides**. Both images are inspected and compared: the page shows the two analyzed images side by side, the defects on each side, the differences between them, and what to change for each defect type. The conveyor moves backward if either side has a defect and forward only if both sides are good.

In **Two sides** mode, **Start two-side conveyor** runs forward for 3 seconds, stops and waits for the configured settle time, then captures the front. After front capture, the conveyor runs backward for the saved **Two sides: feed forward** time and stops. A **Turn your PCB** popup gives you 8 seconds to flip the board while the belt stays stopped. At the end of the countdown, the conveyor runs forward for that same saved feed time, stops, and only then captures the back. Both sides are analyzed and saved in **Scan history**; the combined result controls the existing good/defect sorting movement. **Cancel and stop conveyor** cancels the countdown and prevents back capture or sorting. Manual capture and uploads remain available.

Use **Save dashboard setup** to remember One side or Two sides in this browser. In **Cycle timings** (also shown below two-side inspection), save a named timing and select **Use** to keep it in Firebase. **Two sides: feed forward** defaults to 3 seconds and **Two sides: turn PCB** defaults to 8 seconds. Existing saved timings use these defaults until edited. Results are saved automatically by the backend, including both images and their comparison.

On **History**, **Export PDF** downloads a report with scan totals, every defect type sorted from least to most detected with its average, lowest and highest confidence and the suggested fix, the two-side comparisons, and the scan log.

## Firebase conveyor control

The provided Firebase web configuration is stored in `src/firebaseConfig.js`. The conveyor writes the numeric value at `ks5791/Direction` in the Realtime Database:

- **Stop:** `0`
- **Forward:** `1`
- **Backward:** `2`

Press **Start conveyor** (on **Conveyor control** or **Live inspection**) to run one timed cycle for one board:

1. Forward (`1`) for 2 seconds to bring the PCB under the camera, then stop (`0`).
2. Wait 1 second for the belt to settle, then compare camera frames every 0.25 seconds and capture only when the picture stops changing (up to 5 seconds; after that the latest frame is used). Run best.pt on that still frame.
3. **Good PCB** (a class named **Good Pcb** or another recognized good-board label): forward (`1`) for 4 seconds, then stop.
4. **Defective PCB** (any defect class; defects take precedence over good-board detections): backward (`2`) for 4 seconds, then stop.
5. **No PCB in the frame / no confident result:** the conveyor stays stopped.

**Stop conveyor** cancels the cycle at any point and sends `0`. Press **Start conveyor** again for the next board.

### Conveyor timings

The times above are the built-in **Default** timing (feed 2 s, settle 1 s, good 4 s, defect 4 s). On **Conveyor control → Cycle timings** you can add your own named timings, edit or delete them, and press **Use** to choose which one the next cycle runs. Each time can be 0.1–60 seconds (settle can be 0). Timings cannot be changed while a cycle is running.

Timings are stored in the same Realtime Database:

- `ks5791/ConveyorTimings/{id}`: `{ name, feedSeconds, settleSeconds, goodSeconds, defectSeconds, updatedAt }`
- `ks5791/SelectedTiming`: the id of the timing in use (missing means Default)

The database rules must allow this app to read and write both paths.

The app uses Firebase's Realtime Database REST endpoint. The web configuration identifies the project but does not grant database access; the database rules must allow this app to read and write `ks5791/Direction`. Firebase permission and network failures are shown in the control panel. If the initial stop command cannot be written, the scan is not started.

**Accuracy:** Five originals per defect is only the minimum to begin training. Generated variations do not count as independent observations or guarantee 90% accuracy. Collect varied boards, lighting, viewing angles, and normal boards, and evaluate on a separate test set before relying on inspection results. The dashboard reports validation mAP, which is an object detection metric, not an overall accuracy percentage. The supplied best.pt is independent of the Training studio dataset.

## API

The local API exposes `/api/health`, `/api/classes`, `PATCH /api/classes/{class_id}/target`, `/api/samples`, `/api/train`, `/api/detect`, `/api/detect-pair` (form fields `front` and `back`), `/api/report.pdf`, and `/api/history`. `/api/detect` runs best.pt on the full image when `roi` is omitted; an optional `roi` form field with normalized `{ "x", "y", "w", "h" }` coordinates selects a manual region. Interactive API docs are available at `http://127.0.0.1:8000/docs` while the server is running.


python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000