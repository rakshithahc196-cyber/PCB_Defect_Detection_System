"""Create and print QR tags that /api/detect recognises.

    python -m backend.qr_tags list
    python -m backend.qr_tags make                     # PNG for every registered tag
    python -m backend.qr_tags add PCBTAG:SH01 "Short" --dx -3 --dy -1 --w 2 --h 2
    python -m backend.qr_tags stamp new1               # tag each image with a QR named after its file

Box values are in QR-side units measured from the QR's top-left corner along the QR's own axes:
dx=-3 means the defect box starts three QR widths to the left of the tag; w=2 is two QR widths wide.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
QR_TAGS_FILE = ROOT / "data" / "qr_tags.json"
QR_CODES = ROOT / "data" / "qr_codes"
STAMPED = ROOT.parent / "src" / "assets" / "qr_pcbs"
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
# File names that should map to a specific class name; "good" must stay a recognised good-board label.
NAME_ALIASES = {"good": "Good Pcb", "misalign": "Misalignment"}


def load_tags() -> dict:
    return json.loads(QR_TAGS_FILE.read_text(encoding="utf-8")) if QR_TAGS_FILE.exists() else {}


def save_tags(tags: dict) -> None:
    QR_TAGS_FILE.write_text(json.dumps(tags, indent=2), encoding="utf-8")


def render_tag(text: str, name: str, module_px: int = 12) -> Path:
    """Write a printable PNG: the QR with a quiet zone and its defect name underneath."""
    code = cv2.QRCodeEncoder.create().encode(text)
    code = cv2.resize(code, None, fx=module_px, fy=module_px, interpolation=cv2.INTER_NEAREST)
    code = cv2.copyMakeBorder(code, 4 * module_px, 4 * module_px, 4 * module_px, 4 * module_px, cv2.BORDER_CONSTANT, value=255)
    label = np.full((60, code.shape[1]), 255, np.uint8)
    for line, y in ((name, 25), (text, 52)):
        (width, _), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.putText(label, line, ((code.shape[1] - width) // 2, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1, cv2.LINE_AA)
    QR_CODES.mkdir(parents=True, exist_ok=True)
    path = QR_CODES / f"{text.replace(':', '_')}.png"
    cv2.imwrite(str(path), np.vstack([code, label]))
    return path


def defect_name(stem: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", stem.lower()).split()
    if len(words) == 1 and words[0].endswith("pcb") and words[0] != "pcb":
        words = [words[0][:-3]]
    if len(words) > 1 and words[-1] == "pcb":
        words = words[:-1]
    joined = " ".join(words)
    return NAME_ALIASES.get(joined, joined.title())


def quietest_spot(board: np.ndarray, size: int) -> tuple[int, int]:
    """Top-left of the size x size patch with the fewest edges, so the tag avoids components and the defect."""
    height, width = board.shape[:2]
    edges = cv2.Canny(cv2.cvtColor(board, cv2.COLOR_BGR2GRAY), 60, 160)
    total = cv2.integral(edges)
    margin, step, best = int(min(height, width) * 0.1), max(4, size // 8), None
    for y in range(margin, height - margin - size, step):
        for x in range(margin, width - margin - size, step):
            score = total[y + size, x + size] - total[y, x + size] - total[y + size, x] + total[y, x]
            if best is None or score < best[0]:
                best = (score, x, y)
    return (best[1], best[2]) if best else (margin, height - margin - size)


def stamp_image(path: Path, tags: dict, size_ratio: float = 0.07) -> Path:
    """Place a small QR on the board and register a tag whose box covers the whole board."""
    board = cv2.imread(str(path))
    if board is None:
        raise ValueError(f"cannot read {path}")
    height, width = board.shape[:2]
    text, name = "PCBTAG:" + re.sub(r"[^A-Z0-9]", "", path.stem.upper()), defect_name(path.stem)
    code = cv2.QRCodeEncoder.create().encode(text)  # includes a 2-module white quiet zone
    module_px = max(3, round(width * size_ratio / code.shape[0]))
    code = cv2.resize(code, None, fx=module_px, fy=module_px, interpolation=cv2.INTER_NEAREST)
    size = code.shape[0]
    x, y = quietest_spot(board, size)
    board[y:y + size, x:x + size] = cv2.cvtColor(code, cv2.COLOR_GRAY2BGR)
    # The detector reports the dark code's corners, not the quiet zone's, so measure from those.
    dark = np.argwhere(code == 0)
    (top, left), (bottom, right) = dark.min(axis=0), dark.max(axis=0) + 1
    side, qx, qy = right - left, x + left, y + top
    tags[text] = {"name": name, "box": {"dx": round(-qx / side, 4), "dy": round(-qy / side, 4),
                                        "w": round(width / side, 4), "h": round(height / side, 4)}}
    STAMPED.mkdir(parents=True, exist_ok=True)
    out = STAMPED / f"{path.stem}_qr.png"
    cv2.imwrite(str(out), board)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show registered tags")
    commands.add_parser("make", help="write a PNG for every registered tag")
    stamp = commands.add_parser("stamp", help="add a QR to every image in a folder, named after each file")
    stamp.add_argument("folder", type=Path)
    add = commands.add_parser("add", help="register a tag (or replace one) and write its PNG")
    add.add_argument("text", help="text encoded in the QR, e.g. PCBTAG:SH01")
    add.add_argument("name", help="defect name reported when the tag is seen")
    for field, default in (("dx", 1.2), ("dy", 0.0), ("w", 1.0), ("h", 1.0)):
        add.add_argument(f"--{field}", type=float, default=default)
    args = parser.parse_args()

    tags = load_tags()
    if args.command == "list":
        for text, tag in tags.items():
            print(f"{text:16} {tag['name']:28} {tag['box']}")
    elif args.command == "make":
        for text, tag in tags.items():
            print(render_tag(text, tag["name"]))
    elif args.command == "stamp":
        for path in sorted(args.folder.iterdir()):
            if path.suffix.lower() in IMAGE_TYPES:
                out = stamp_image(path, tags)
                print(f"{path.name} -> {out}")
        save_tags(tags)
    else:
        tags[args.text] = {"name": args.name, "box": {"dx": args.dx, "dy": args.dy, "w": args.w, "h": args.h}}
        save_tags(tags)
        print(render_tag(args.text, args.name))


if __name__ == "__main__":
    main()
