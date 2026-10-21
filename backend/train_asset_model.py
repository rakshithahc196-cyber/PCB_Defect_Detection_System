"""Train a fast YOLO detector from the QR-free images in training_no_qr."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml
from PIL import Image, ImageEnhance, ImageOps
from ultralytics import YOLO

from backend import app as api


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "training_no_qr"
DATASET = SOURCE / "dataset"
RUNS = SOURCE / "runs"

# Normalized tight boxes derived from the registered, pre-removal tag geometry.
# Misalignment has several separate rotated parts rather than one whole-board box.
ITEMS = [
    ("misalignment.png", "Misalignment", [
        (0.16, 0.18, 0.11, 0.15), (0.44, 0.09, 0.10, 0.13),
        (0.69, 0.11, 0.13, 0.19), (0.69, 0.45, 0.10, 0.12),
        (0.69, 0.67, 0.09, 0.12),
    ]),
    ("burnt.png", "Burnt", [(0.3969, 0.4156, 0.1980, 0.1794)]),
    ("circuit_breakoff.png", "Circuit Breakoff", [(0.0000, 0.6144, 0.1070, 0.2108)]),
    ("excess_solder.png", "Excess Solder", [(0.4042, 0.6429, 0.2325, 0.1675)]),
    ("ic_burnout.png", "IC Burnout", [(0.0514, 0.2827, 0.2650, 0.1371)]),
    # Include a little context around this very narrow joint. At inference size
    # the original 28-pixel-wide box was too small for YOLO's feature maps.
    ("insufficient_solder.png", "Insufficient Solder", [(0.6200, 0.6250, 0.0600, 0.1200)]),
    ("missing_component.png", "Missing Component", [(0.6037, 0.2928, 0.1936, 0.3434)]),
    ("missing_drivers.png", "Missing Drivers", [(0.0725, 0.2987, 0.3215, 0.2636)]),
    ("missing_microcontroller.png", "Missing Microcontroller", [(0.1866, 0.6313, 0.1713, 0.2633)]),
    ("open_circuit.png", "Open Circuit", [(0.3609, 0.2420, 0.3412, 0.7029)]),
]


def transform_box(box: tuple[float, float, float, float], mirror: bool, flip: bool) -> tuple[float, float, float, float]:
    x, y, width, height = box
    if mirror:
        x = 1 - x - width
    if flip:
        y = 1 - y - height
    return x, y, width, height


def label_line(class_index: int, box: tuple[float, float, float, float]) -> str:
    x, y, width, height = box
    return f"{class_index} {x + width / 2:.6f} {y + height / 2:.6f} {width:.6f} {height:.6f}"


def prepare_dataset(variants: int = 8) -> Path:
    if DATASET.exists():
        shutil.rmtree(DATASET)
    for split in ("train", "val"):
        (DATASET / "images" / split).mkdir(parents=True)
        (DATASET / "labels" / split).mkdir(parents=True)

    manifest = []
    for class_index, (filename, name, boxes) in enumerate(ITEMS):
        source = SOURCE / filename
        if not source.exists():
            raise FileNotFoundError(f"Missing QR-free source: {source}")
        with Image.open(source) as opened:
            base = opened.convert("RGB")
        base.thumbnail((1280, 1280), Image.Resampling.LANCZOS)

        # The original is included so the requested exact image is learned.
        # Mirrored/color variants reduce pure pixel memorization while keeping
        # every defect box geometrically correct.
        for variant in range(variants):
            mirror, flip = variant % 4 in (1, 3), variant % 4 in (2, 3)
            image = ImageOps.mirror(base) if mirror else base.copy()
            image = ImageOps.flip(image) if flip else image
            # Variant zero must be the unmodified requested source image. This
            # is especially important for small, low-contrast solder defects.
            if variant:
                image = ImageEnhance.Brightness(image).enhance(0.88 + (variant % 4) * 0.07)
                image = ImageEnhance.Contrast(image).enhance(0.92 + (variant % 3) * 0.07)
            stem = f"{class_index:02d}_{Path(filename).stem}_{variant:02d}"
            image.save(DATASET / "images" / "train" / f"{stem}.jpg", quality=92)
            changed = [transform_box(box, mirror, flip) for box in boxes]
            (DATASET / "labels" / "train" / f"{stem}.txt").write_text(
                "\n".join(label_line(class_index, box) for box in changed) + "\n", encoding="utf-8"
            )

        validation = ImageEnhance.Brightness(base).enhance(0.96)
        validation.save(DATASET / "images" / "val" / f"{class_index:02d}_{Path(filename).stem}.jpg", quality=94)
        (DATASET / "labels" / "val" / f"{class_index:02d}_{Path(filename).stem}.txt").write_text(
            "\n".join(label_line(class_index, box) for box in boxes) + "\n", encoding="utf-8"
        )
        manifest.append({"class": name, "source": filename, "boxes": boxes})

    config = {
        "path": str(DATASET.resolve()), "train": "images/train", "val": "images/val",
        "names": {index: item[1] for index, item in enumerate(ITEMS)},
    }
    config_path = DATASET / "data.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    (SOURCE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return config_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--variants", type=int, default=8)
    parser.add_argument(
        "--weights", type=Path, default=ROOT / "yolo11n.pt",
        help="Starting weights. Use backend/data/model.pt for a short fine-tune.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = prepare_dataset(args.variants)
    run_name = "asset_model"
    print(f"Prepared {len(ITEMS) * args.variants} training images and 10 validation images.", flush=True)
    model = YOLO(str(args.weights))
    result = model.train(
        data=str(config_path), epochs=args.epochs, imgsz=512, batch=8, workers=0,
        project=str(RUNS), name=run_name, exist_ok=True, plots=False, verbose=True,
        patience=12, cache=True,
    )
    best = RUNS / run_name / "weights" / "best.pt"
    if not best.exists():
        raise RuntimeError("Training completed without best.pt")
    if api.MODEL.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(api.MODEL, api.DATA / f"model-before-assets-{stamp}.pt")
    staged = api.DATA / "model.assets.new.pt"
    shutil.copy2(best, staged)
    staged.replace(api.MODEL)

    box_metrics = getattr(result, "box", None)
    metrics = {
        "map50": round(float(box_metrics.map50), 4) if box_metrics is not None else None,
        "map50_95": round(float(box_metrics.map), 4) if box_metrics is not None else None,
        "precision": round(float(box_metrics.mp), 4) if box_metrics is not None else None,
        "recall": round(float(box_metrics.mr), 4) if box_metrics is not None else None,
    }
    with api.lock:
        state = api.read_state()
        state["trained_at"] = datetime.now(timezone.utc).isoformat()
        state["trained_signature"] = api.dataset_signature(state)
        state["metrics"] = metrics
        state["model_source"] = "training_no_qr"
        api.write_state(state)
    print(f"Installed {best} -> {api.MODEL}", flush=True)
    print(f"Metrics: {metrics}", flush=True)


if __name__ == "__main__":
    main()
