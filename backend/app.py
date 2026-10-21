"""Local PCB defect detection API. Run with: uvicorn backend.app:app --reload"""

from __future__ import annotations

import io
import asyncio
import hashlib
import json
import math
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from .green_board import crop_green_board, share_inside
from .ip_camera import IpCamera, IpCameraError
from .report import build_report_pdf, compare_sides


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SAMPLES = DATA / "samples"
DETECTIONS = DATA / "detections"
MODEL = ROOT.parent / "best.pt"
STATE_FILE = DATA / "state.json"
MAX_UPLOAD = 12 * 1024 * 1024
MIN_SAMPLES_PER_CLASS = 5
MAX_TRAINING_IMAGES_PER_CLASS = 500
MAX_DEFECT_BOX_AREA = 0.75
TARGET_BOARD_LEVEL = 55.0  # median board brightness (0–255); only boards darker than this are lifted to it
MAX_BRIGHTEN = 2.0
SINGLE_VIEW_CONFIDENCE = 0.5  # a detection found in only one of the two orientations must reach this
SAME_DEFECT_IOU = 0.3  # boxes from the two orientations overlapping this much are the same detection
MIN_DEFECT_ON_BOARD = 0.8  # share of a defect box that must lie on the green board
EDGE_TO_EDGE = 0.02  # a defect box within this of two opposite crop edges runs edge to edge and is an artifact
GOOD_BOARD_LABELS = {"goodpcb", "goodboard", "normalpcb", "normalboard", "nodefect", "defectfree"}
for directory in (DATA, SAMPLES, DETECTIONS):
    directory.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(DATA))

app = FastAPI(title="PCB Vision API")
lock = threading.RLock()
train_state = {"status": "idle", "message": "", "started_at": None, "metrics": None}
inference_model = None
inference_model_mtime = None
inference_lock = threading.Lock()
ip_camera = IpCamera()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {"classes": [], "samples": [], "history": [], "scan_count": 0, "defect_count": 0, "trained_at": None, "metrics": None}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def write_state(state: dict) -> None:
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(STATE_FILE)


def dataset_signature(state: dict) -> str:
    payload = {"classes": state["classes"], "samples": state["samples"]}
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def class_summary(state: dict) -> list[dict]:
    summaries = []
    for item in state["classes"]:
        count = sum(sample["class_id"] == item["id"] for sample in state["samples"])
        summaries.append({**item, "count": count, "training_count": max(count, item.get("target_count", 0))})
    return summaries


def oversized_defect_labels(state: dict) -> int:
    defect_ids = {
        item["id"] for item in state["classes"]
        if "".join(character for character in item["name"].lower() if character.isalnum()) not in GOOD_BOARD_LABELS
    }
    return sum(
        sample["class_id"] in defect_ids and sample.get("box") is not None
        and sample["box"]["w"] * sample["box"]["h"] > MAX_DEFECT_BOX_AREA
        for sample in state["samples"]
    )


def get_image(data: bytes) -> Image.Image:
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Image is larger than 12 MB")
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.verify()
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(400, "Upload a valid image") from exc
    if image.width < 64 or image.height < 64:
        raise HTTPException(400, "Image must be at least 64 × 64 pixels")
    if image.width * image.height > 25_000_000:
        raise HTTPException(413, "Image dimensions are too large")
    return image


class NewClass(BaseModel):
    name: str = Field(min_length=2, max_length=50)


class ExpansionTarget(BaseModel):
    target_count: int = Field(ge=MIN_SAMPLES_PER_CLASS, le=MAX_TRAINING_IMAGES_PER_CLASS)


class IpCameraAddress(BaseModel):
    address: str = Field(min_length=2, max_length=60)


class SampleBoxUpdate(BaseModel):
    box: dict


def validate_sample_box(coords: dict, allow_large: bool = False) -> dict:
    try:
        x, y, width, height = (float(coords[key]) for key in ("x", "y", "w", "h"))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, "Draw a valid defect box") from exc
    if not all(map(math.isfinite, (x, y, width, height))) or not (
        0 <= x < 1 and 0 <= y < 1 and 0.005 <= width <= 1 - x and 0.005 <= height <= 1 - y
    ):
        raise HTTPException(400, "Defect box must be inside the image")
    if not allow_large and width * height > MAX_DEFECT_BOX_AREA:
        raise HTTPException(400, "Draw a tighter box around the defect. A whole-board box teaches the model to detect background.")
    return {"x": x, "y": y, "w": width, "h": height}


@app.get("/api/health")
def health():
    with lock:
        state = read_state()
        model_error = None
        model_classes = []
        try:
            with inference_lock:
                model_classes = [{"id": index, "name": name} for index, name in load_model().names.items()]
        except Exception as exc:
            model_error = str(exc)
        model_exists = model_error is None
        return {
            "model_ready": model_exists,
            "model_stale": False,
            "model_file": MODEL.name,
            "model_classes": model_classes,
            "model_error": model_error,
            "trained_at": None,
            "metrics": None,
            "training": dict(train_state),
            "classes": class_summary(state),
            "sample_count": len(state["samples"]),
            "oversized_defect_labels": oversized_defect_labels(state),
            "scan_count": state.get("scan_count", len(state["history"])),
            "defect_count": state.get("defect_count", sum(len(item["findings"]) for item in state["history"])),
        }


@app.get("/api/classes")
def classes():
    with lock:
        state = read_state()
        return {"classes": class_summary(state), "samples": state["samples"]}


@app.post("/api/classes")
def add_class(payload: NewClass):
    name = " ".join(payload.name.strip().split())
    if len(name) < 2:
        raise HTTPException(400, "Enter a defect name")
    with lock:
        state = read_state()
        if any(item["name"].casefold() == name.casefold() for item in state["classes"]):
            raise HTTPException(409, "This defect name already exists")
        item = {"id": uuid.uuid4().hex, "name": name, "created_at": now()}
        state["classes"].append(item)
        write_state(state)
    return item


@app.patch("/api/classes/{class_id}/target")
def set_expansion_target(class_id: str, payload: ExpansionTarget):
    with lock:
        state = read_state()
        item = next((item for item in state["classes"] if item["id"] == class_id), None)
        if item is None:
            raise HTTPException(404, "Defect class not found")
        count = sum(sample["class_id"] == class_id for sample in state["samples"])
        if count < MIN_SAMPLES_PER_CLASS:
            raise HTTPException(400, "Collect at least 5 original images before expanding samples")
        if payload.target_count < count:
            raise HTTPException(400, f"Target must be at least the {count} original images already collected")
        item["target_count"] = payload.target_count
        write_state(state)
        return {**item, "count": count, "training_count": payload.target_count}


@app.post("/api/samples")
async def add_sample(
    class_id: str = Form(...),
    box: str = Form(""),
    file: UploadFile = File(...),
):
    if class_id == "normal":
        sample_box = None
    else:
        try:
            coords = json.loads(box)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(400, "Draw a valid defect box") from exc
        sample_box = None
    image = get_image(await file.read(MAX_UPLOAD + 1))
    with lock:
        state = read_state()
        defect_class = next((item for item in state["classes"] if item["id"] == class_id), None)
        if class_id != "normal" and defect_class is None:
            raise HTTPException(404, "Defect class not found")
        if defect_class is not None:
            normalized_name = "".join(character for character in defect_class["name"].lower() if character.isalnum())
            sample_box = validate_sample_box(coords, allow_large=normalized_name in GOOD_BOARD_LABELS)
        sample_id = uuid.uuid4().hex
        image.save(SAMPLES / f"{sample_id}.jpg", quality=92)
        sample = {"id": sample_id, "class_id": class_id, "box": sample_box, "created_at": now(), "image_url": f"/api/samples/{sample_id}/image"}
        state["samples"].append(sample)
        write_state(state)
    return sample


@app.patch("/api/samples/{sample_id}")
def update_sample_box(sample_id: str, payload: SampleBoxUpdate):
    with lock:
        state = read_state()
        sample = next((item for item in state["samples"] if item["id"] == sample_id), None)
        if sample is None:
            raise HTTPException(404, "Sample not found")
        defect_class = next((item for item in state["classes"] if item["id"] == sample["class_id"]), None)
        if defect_class is None or "".join(c for c in defect_class["name"].lower() if c.isalnum()) in GOOD_BOARD_LABELS:
            raise HTTPException(400, "Only defect sample boxes can be edited")
        sample["box"] = validate_sample_box(payload.box)
        write_state(state)
        return sample


@app.get("/api/samples/{sample_id}/image")
def sample_image(sample_id: str):
    with lock:
        if not any(item["id"] == sample_id for item in read_state()["samples"]):
            raise HTTPException(404, "Sample not found")
    return FileResponse(SAMPLES / f"{sample_id}.jpg", media_type="image/jpeg")


@app.delete("/api/samples/{sample_id}")
def delete_sample(sample_id: str):
    with lock:
        state = read_state()
        if not any(item["id"] == sample_id for item in state["samples"]):
            raise HTTPException(404, "Sample not found")
        state["samples"] = [item for item in state["samples"] if item["id"] != sample_id]
        write_state(state)
        (SAMPLES / f"{sample_id}.jpg").unlink(missing_ok=True)
    return {"ok": True}


def yolo_label(class_index: int, box: dict) -> str:
    cx = box["x"] + box["w"] / 2
    cy = box["y"] + box["h"] / 2
    return f"{class_index} {cx:.6f} {cy:.6f} {box['w']:.6f} {box['h']:.6f}\n"


def augment_sample(source: Path, destination: Path, box: dict, variant: int) -> dict:
    """Create a visual variation and update its box for any mirrored axes."""
    with Image.open(source) as original:
        image = original.convert("RGB")
    image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    changed_box = dict(box)
    if variant % 4 in (1, 3):
        image = ImageOps.mirror(image)
        changed_box["x"] = 1 - box["x"] - box["w"]
    if variant % 4 in (2, 3):
        image = ImageOps.flip(image)
        changed_box["y"] = 1 - box["y"] - box["h"]
    image = ImageEnhance.Brightness(image).enhance(0.82 + (variant * 7 % 17) * 0.025)
    image = ImageEnhance.Contrast(image).enhance(0.88 + (variant * 11 % 13) * 0.02)
    image = ImageEnhance.Color(image).enhance(0.9 + (variant * 3 % 11) * 0.02)
    image.save(destination, quality=90)
    return changed_box


def train_worker(classes_snapshot: list[dict], samples_snapshot: list[dict], signature: str) -> None:
    global inference_model
    try:
        from ultralytics import YOLO

        run_id = uuid.uuid4().hex[:10]
        dataset = DATA / "training" / run_id
        for split in ("train", "val"):
            (dataset / "images" / split).mkdir(parents=True)
            (dataset / "labels" / split).mkdir(parents=True)
        class_ids = [item["id"] for item in classes_snapshot]
        for class_index, class_id in enumerate(class_ids):
            items = sorted((s for s in samples_snapshot if s["class_id"] == class_id), key=lambda s: s["id"])
            training_sources = []
            for index, sample in enumerate(items):
                split = "val" if index % 5 == 0 else "train"
                source = SAMPLES / f"{sample['id']}.jpg"
                if not source.exists():
                    raise RuntimeError("A training image is missing. Remove its sample and retry.")
                shutil.copy2(source, dataset / "images" / split / source.name)
                (dataset / "labels" / split / f"{sample['id']}.txt").write_text(yolo_label(class_index, sample["box"]), encoding="utf-8")
                if split == "train":
                    training_sources.append((source, sample["box"]))
            target_count = max(len(items), classes_snapshot[class_index].get("target_count", 0))
            for generated in range(target_count - len(items)):
                source, source_box = training_sources[generated % len(training_sources)]
                name = f"aug_{class_index}_{generated:04d}"
                new_box = augment_sample(source, dataset / "images" / "train" / f"{name}.jpg", source_box, generated + 1)
                (dataset / "labels" / "train" / f"{name}.txt").write_text(yolo_label(class_index, new_box), encoding="utf-8")
        normal_items = sorted((s for s in samples_snapshot if s["class_id"] == "normal"), key=lambda s: s["id"])
        for index, sample in enumerate(normal_items):
            split = "val" if index % 5 == 0 else "train"
            source = SAMPLES / f"{sample['id']}.jpg"
            if not source.exists():
                raise RuntimeError("A training image is missing. Remove its sample and retry.")
            shutil.copy2(source, dataset / "images" / split / source.name)
            (dataset / "labels" / split / f"{sample['id']}.txt").write_text("", encoding="utf-8")
        config = {"path": str(dataset.resolve()), "train": "images/train", "val": "images/val", "names": {i: item["name"] for i, item in enumerate(classes_snapshot)}}
        config_file = dataset / "data.yaml"
        config_file.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        with lock:
            train_state["message"] = "Fine-tuning YOLO on your labeled PCB images…"
        model = YOLO("yolo11n.pt")
        result = model.train(data=str(config_file), epochs=50, imgsz=640, batch=8, project=str(DATA / "runs"), name=run_id, exist_ok=True, plots=False, verbose=False)
        weights = DATA / "runs" / run_id / "weights" / "best.pt"
        if not weights.exists():
            raise RuntimeError("Training finished without a model checkpoint")
        staged = DATA / "model.new.pt"
        shutil.copy2(weights, staged)
        with inference_lock:
            staged.replace(DATA / "model.pt")
            inference_model = None
        box_metrics = getattr(result, "box", None)
        metrics = {
            "map50": round(float(box_metrics.map50), 4) if box_metrics is not None else None,
            "map50_95": round(float(box_metrics.map), 4) if box_metrics is not None else None,
            "precision": round(float(box_metrics.mp), 4) if box_metrics is not None else None,
            "recall": round(float(box_metrics.mr), 4) if box_metrics is not None else None,
        }
        with lock:
            state = read_state()
            state["trained_at"] = now()
            state["metrics"] = metrics
            state["trained_signature"] = signature
            write_state(state)
            train_state.update(status="complete", message="Model ready for inspection", metrics=metrics)
    except Exception as exc:
        with lock:
            train_state.update(status="failed", message=str(exc))


@app.post("/api/train")
def start_training():
    with lock:
        if train_state["status"] == "running":
            raise HTTPException(409, "Training is already running")
        state = read_state()
        if not state["classes"]:
            raise HTTPException(400, "Add a defect class first")
        if oversized_defect_labels(state):
            raise HTTPException(400, "Review and replace oversized defect labels before training")
        counts = class_summary(state)
        missing = [item["name"] for item in counts if item["count"] < MIN_SAMPLES_PER_CLASS]
        if missing:
            raise HTTPException(400, f"Add 5 original labeled samples for each class: {', '.join(missing)}")
        train_state.update(status="running", message="Preparing your dataset…", started_at=now(), metrics=None)
        thread = threading.Thread(target=train_worker, args=(state["classes"], state["samples"], dataset_signature(state)), daemon=True)
        thread.start()
    return {"status": "running"}


def spans_edge_to_edge(box: dict) -> bool:
    return (box["x"] <= EDGE_TO_EDGE and box["x"] + box["w"] >= 1 - EDGE_TO_EDGE) or (
        box["y"] <= EDGE_TO_EDGE and box["y"] + box["h"] >= 1 - EDGE_TO_EDGE)


def is_good_label(name: str) -> bool:
    return "".join(character for character in name.lower() if character.isalnum()) in GOOD_BOARD_LABELS


def crop_inspection_area(image: Image.Image, roi: str) -> Image.Image:
    """Limit inference and the saved scan to the board area selected by the user."""
    if not roi:
        raise HTTPException(400, "Select the PCB area before scanning")
    try:
        selection = json.loads(roi)
        x, y, width, height = (float(selection[key]) for key in ("x", "y", "w", "h"))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, "Select a valid PCB area") from exc
    if not all(map(math.isfinite, (x, y, width, height))) or not (
        0 <= x < 1 and 0 <= y < 1 and 0.05 <= width <= 1 - x and 0.05 <= height <= 1 - y
    ):
        raise HTTPException(400, "PCB area must be inside the image")
    left, top = round(x * image.width), round(y * image.height)
    right, bottom = round((x + width) * image.width), round((y + height) * image.height)
    if right - left < 64 or bottom - top < 64:
        raise HTTPException(400, "Select a larger PCB area (at least 64 × 64 pixels)")
    return image.crop((left, top, right, bottom))


def load_model():
    """Load only the supplied checkpoint; caller holds inference_lock."""
    global inference_model, inference_model_mtime
    if not MODEL.is_file():
        raise RuntimeError("Place best.pt in the project root to enable detection")
    model_mtime = MODEL.stat().st_mtime_ns
    if inference_model is None or inference_model_mtime != model_mtime:
        from ultralytics import YOLO
        model = YOLO(str(MODEL))
        if model.task != "detect":
            raise RuntimeError("best.pt must be a YOLO object detection model")
        inference_model = model
        inference_model_mtime = model_mtime
    return inference_model


def enhance_for_inference(image: Image.Image) -> Image.Image:
    """Webcam frames are washed out next to the training photos; restore colour and contrast.

    Sharpening is deliberately left out: on blurred frames it creates false circuit-breakdown hits.
    """
    image = ImageEnhance.Contrast(ImageEnhance.Color(image.convert("RGB")).enhance(1.4)).enhance(1.3)
    # Dark solder mask under weak light hides burns and missing parts; lift the board, not the painted-out background.
    luminance = np.asarray(image.convert("L"), dtype=np.float32)
    board = luminance[luminance < 250]
    if board.size and (level := float(np.median(board))) < TARGET_BOARD_LEVEL:
        image = ImageEnhance.Brightness(image).enhance(min(MAX_BRIGHTEN, TARGET_BOARD_LEVEL / max(level, 1.0)))
    return image


class _Values:
    """Mimics the tensor .tolist() interface of an Ultralytics result."""

    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


def _iou(a: list, b: list) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    overlap = width * height
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    return overlap / union if union > 0 else 0.0


def merge_orientations(upright: list, flipped: list, confidence: float) -> list:
    """Combine (box, conf, cls) detections from the upright and 180°-turned image.

    Boards reach the camera either way round, and best.pt was trained mostly one way, so each
    orientation finds defects the other misses. A detection both agree on is kept from the normal
    threshold; one seen in a single orientation must be confident on its own.
    """
    tagged = [(*item, 0) for item in upright] + [(*item, 1) for item in flipped]
    tagged.sort(key=lambda item: item[1], reverse=True)
    kept = []
    used = [False] * len(tagged)
    for i, (box, score, cls, view) in enumerate(tagged):
        if used[i]:
            continue
        used[i] = True
        views = {view}
        for j in range(i + 1, len(tagged)):
            other_box, _, other_cls, other_view = tagged[j]
            if not used[j] and other_cls == cls and _iou(box, other_box) >= SAME_DEFECT_IOU:
                used[j] = True
                views.add(other_view)
        if score >= confidence and (len(views) == 2 or score >= SINGLE_VIEW_CONFIDENCE):
            kept.append((box, score, cls))
    return kept


def predict_yolo(image: Image.Image, confidence: float):
    with inference_lock:
        try:
            model = load_model()
            # Run at the size best.pt was trained at; a different size shifts object scale and loses detections.
            size = model.overrides.get("imgsz") or 640
            enhanced = enhance_for_inference(image)
            width, height = enhanced.size
            views = []
            for turned in (False, True):
                source = enhanced.rotate(180) if turned else enhanced
                # Test-time augmentation (flips and scales) lifts confidence on small, blurred camera crops.
                result = model.predict(source=source, conf=confidence, imgsz=size, augment=True, verbose=False)[0]
                found = []
                if result.boxes is not None:
                    for (x1, y1, x2, y2), score, cls in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), result.boxes.cls.tolist()):
                        box = [width - x2, height - y2, width - x1, height - y1] if turned else [x1, y1, x2, y2]
                        found.append((box, float(score), int(cls)))
                views.append(found)
            kept = merge_orientations(*views, confidence)
            boxes = SimpleNamespace(xyxy=_Values([box for box, _, _ in kept]), conf=_Values([score for _, score, _ in kept]),
                                    cls=_Values([cls for _, _, cls in kept]))
            return SimpleNamespace(names=model.names, boxes=boxes)
        except Exception as exc:
            raise HTTPException(500, f"Detection failed: {exc}") from exc


@app.post("/api/detect")
async def detect(file: UploadFile = File(...), roi: str = Form(""), full_view: bool = Form(False)):
    """full_view: a live camera frame, where the whole board must be visible."""
    return await run_inspection(await file.read(MAX_UPLOAD + 1), roi, full_view=full_view)


@app.post("/api/detect-pair")
async def detect_pair(front: UploadFile = File(...), back: UploadFile = File(...)):
    """Inspect both sides of one board and compare them."""
    front_data, back_data = await front.read(MAX_UPLOAD + 1), await back.read(MAX_UPLOAD + 1)
    get_image(front_data), get_image(back_data)  # reject a bad upload before either side is saved
    pair_id = uuid.uuid4().hex
    front_scan = await run_inspection(front_data, side="front", pair_id=pair_id)
    back_scan = await run_inspection(back_data, side="back", pair_id=pair_id)
    pair = {"id": pair_id, "created_at": now(), "front_id": front_scan["id"], "back_id": back_scan["id"],
            "comparison": compare_sides(front_scan, back_scan)}
    with lock:
        state = read_state()
        state["pairs"] = [pair, *state.get("pairs", [])][:50]
        write_state(state)
    return {**pair, "front": front_scan, "back": back_scan}


@app.get("/api/report.pdf")
def report_pdf():
    with lock:
        state = read_state()
    filename = f"pcb-inspection-report-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf"
    return Response(build_report_pdf(state), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


async def run_inspection(data: bytes, roi: str = "", side: str | None = None, pair_id: str | None = None, full_view: bool = False) -> dict:
    if not MODEL.is_file():
        raise HTTPException(409, "Place best.pt in the project root to enable detection")
    image = get_image(data)
    pcb_region = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
    warning = None
    result = None
    board_mask = None
    if roi:
        region_source = "manual"
        image = crop_inspection_area(image, roi)
        pcb_region = json.loads(roi)
    else:
        # Inspect only the green board; a frame without one is not sent to the model.
        status, board = await asyncio.to_thread(crop_green_board, image, full_view)
        if board:
            region_source = "green"
            image, pcb_region, board_mask = board
        else:
            region_source = "none"
            warning = "PCB only partly in view: feed the board further under the camera" if status == "partial" else "No green PCB board found in the frame"
    if region_source != "none":
        result = await asyncio.to_thread(predict_yolo, image, 0.25)
    findings = []
    if result is not None and result.boxes is not None:
        for coords, confidence, class_index in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), result.boxes.cls.tolist()):
            x1, y1, x2, y2 = coords
            name = result.names[int(class_index)]
            box = {"x": x1 / image.width, "y": y1 / image.height, "w": (x2 - x1) / image.width, "h": (y2 - y1) / image.height}
            if board_mask is not None and not is_good_label(name):
                # A defect must sit on the board and must not be a box around the whole crop.
                # Long defects such as cracks may run most of the board, so only boxes touching both opposite edges go.
                if (share_inside(board_mask, box) < MIN_DEFECT_ON_BOARD or box["w"] * box["h"] > MAX_DEFECT_BOX_AREA
                        or spans_edge_to_edge(box)):
                    continue
            findings.append({"name": name, "confidence": round(float(confidence), 4), "box": box})
    scan_id = uuid.uuid4().hex
    image.save(DETECTIONS / f"{scan_id}.jpg", quality=88)
    item = {
        "id": scan_id, "created_at": now(), "findings": findings,
        "pcb_detected": bool(findings), "pcb_region": pcb_region, "region_source": region_source,
        "model_stale": False,
        "model_file": MODEL.name,
        "localization_warning": warning,
        "image_url": f"/api/history/{scan_id}/image",
    }
    if side:
        item.update(side=side, pair_id=pair_id)
    with lock:
        state = read_state()
        state["history"].insert(0, item)
        state["scan_count"] = state.get("scan_count", len(state["history"]) - 1) + 1
        state["defect_count"] = state.get("defect_count", sum(len(scan["findings"]) for scan in state["history"][1:])) + len(findings)
        old_items = state["history"][100:]
        state["history"] = state["history"][:100]
        write_state(state)
        for old in old_items:
            (DETECTIONS / f"{old['id']}.jpg").unlink(missing_ok=True)
    return item


@app.get("/api/history")
def history():
    with lock:
        state = read_state()
        return {"items": state["history"], "pairs": state.get("pairs", [])}


@app.get("/api/history/{scan_id}/image")
def history_image(scan_id: str):
    with lock:
        if not any(item["id"] == scan_id for item in read_state()["history"]):
            raise HTTPException(404, "Scan not found")
    return FileResponse(DETECTIONS / f"{scan_id}.jpg", media_type="image/jpeg")


@app.get("/api/ipcam")
def ip_camera_status():
    return ip_camera.status()


@app.post("/api/ipcam/connect")
async def connect_ip_camera(payload: IpCameraAddress):
    try:
        return await asyncio.to_thread(ip_camera.connect, payload.address)
    except IpCameraError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/ipcam/disconnect")
def disconnect_ip_camera():
    ip_camera.disconnect()
    return ip_camera.status()


@app.get("/api/ipcam/frame")
def ip_camera_frame():
    frame = ip_camera.latest()
    if frame is None:
        raise HTTPException(503, ip_camera.status()["error"] or "IP camera is not sending frames")
    return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/ipcam/stream")
async def ip_camera_stream():
    """Re-serve the camera as MJPEG so the browser can preview it with a plain <img>."""
    if not ip_camera.status()["connected"]:
        raise HTTPException(409, "Connect an IP camera first")

    async def frames():
        last = None
        while ip_camera.status()["connected"]:
            frame = ip_camera.latest()
            if frame is not None and frame is not last:
                last = frame
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
            await asyncio.sleep(0.08)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-store"})
