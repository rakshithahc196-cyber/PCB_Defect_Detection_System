"""Find the green PCB in a camera frame so defect inference only sees the board."""

from __future__ import annotations

import cv2
import numpy as np
from typing import NamedTuple

from PIL import Image

# OpenCV hue runs 0–179. Solder mask ranges from bright yellow-green (~40) to dark blue-green (~105);
# the saturation floor keeps out white and grey tables, which share the hue but carry little colour.
GREEN_LOW = np.array([35, 45, 15], dtype=np.uint8)
GREEN_HIGH = np.array([110, 255, 255], dtype=np.uint8)
MIN_BOARD_AREA = 0.04  # of the frame; smaller green patches are not treated as a board
MIN_GREEN_FILL = 0.25  # share of real green pixels inside the region; dark or grey surfaces fall well below
EDGE_MARGIN = 0.01  # of the frame side; a board this close to an edge is treated as cut off by it
MIN_EDGE_BOARD_AREA = 0.15  # a board cut off by the frame edge must still cover this much of the frame
MAX_WORK_SIDE = 640
PADDING = 0.02  # of the board size, so components on the edge stay in the crop


def _board_contour(rgb: np.ndarray):
    """Largest green region in a downscaled copy, with the scale used, or None."""
    height, width = rgb.shape[:2]
    scale = min(1.0, MAX_WORK_SIDE / max(width, height))
    small = cv2.resize(rgb, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    hsv = cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_RGB2HSV)
    raw = cv2.inRange(hsv, GREEN_LOW, GREEN_HIGH)
    # Close the gaps left by silver pads, white silkscreen and black ICs, then drop specks.
    side = max(5, round(min(small.shape[:2]) * 0.04)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (side, side))
    mask = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    board = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(board)
    if area < MIN_BOARD_AREA * small.shape[0] * small.shape[1]:
        return None
    region = np.zeros_like(raw)
    cv2.drawContours(region, [board], -1, 255, cv2.FILLED)
    if cv2.countNonZero(cv2.bitwise_and(raw, region)) < MIN_GREEN_FILL * area:
        return None
    return board.astype(np.float32) / scale


def find_green_board(image: Image.Image) -> dict | None:
    """Return the board's normalized axis-aligned {x, y, w, h}, or None when no green board is visible."""
    board = _board_contour(np.asarray(image.convert("RGB")))
    if board is None:
        return None
    x, y, w, h = cv2.boundingRect(board)
    return {"x": x / image.width, "y": y / image.height, "w": min(w, image.width - x) / image.width, "h": min(h, image.height - y) / image.height}


class BoardCrop(NamedTuple):
    image: Image.Image  # the straightened board, everything outside its outline painted white
    region: dict  # normalized axis-aligned box in the frame, plus the straightening angle
    mask: np.ndarray  # 255 where the crop is board, 0 where it was background


def crop_green_board(image: Image.Image, require_full_view: bool = True) -> tuple[str, BoardCrop | None]:
    """Cut out just the green board, straightened if it lies at an angle.

    Returns ("ok", crop), ("none", None) when no board is visible, or ("partial", None)
    when only a sliver of a board at the frame edge is visible. Uploaded photos are often cropped tight to the
    board, so callers pass require_full_view=False for them.
    """
    rgb = np.asarray(image.convert("RGB"))
    board = _board_contour(rgb)
    if board is None:
        return "none", None
    x, y, w, h = cv2.boundingRect(board)
    margin_x, margin_y = EDGE_MARGIN * rgb.shape[1], EDGE_MARGIN * rgb.shape[0]
    clipped = x <= margin_x or y <= margin_y or x + w >= rgb.shape[1] - margin_x or y + h >= rgb.shape[0] - margin_y
    # A large board clipped by the frame is still inspected; a sliver at the edge is a board not yet in place.
    if require_full_view and clipped and cv2.contourArea(board) < MIN_EDGE_BOARD_AREA * rgb.shape[0] * rgb.shape[1]:
        return "partial", None
    mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [cv2.convexHull(board.astype(np.int32))], -1, 255, cv2.FILLED)
    (cx, cy), (w, h), angle = cv2.minAreaRect(board)
    # Keep the turn under 45° so the board is straightened, not flipped on its side.
    if angle > 45:
        angle -= 90
        w, h = h, w
    elif angle < -45:
        angle += 90
        w, h = h, w
    w, h = w * (1 + 2 * PADDING), h * (1 + 2 * PADDING)
    if abs(angle) >= 2:
        matrix = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        size = (rgb.shape[1], rgb.shape[0])
        rgb = cv2.warpAffine(rgb, matrix, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        mask = cv2.warpAffine(mask, matrix, size, flags=cv2.INTER_NEAREST, borderValue=0)
    left, top = max(0, round(cx - w / 2)), max(0, round(cy - h / 2))
    right, bottom = min(rgb.shape[1], round(cx + w / 2)), min(rgb.shape[0], round(cy + h / 2))
    if right - left < 64 or bottom - top < 64:
        return "none", None
    crop, crop_mask = rgb[top:bottom, left:right].copy(), mask[top:bottom, left:right]
    # Belt, mesh and table beside the board are not inspected; a few pixels of margin keep edge parts.
    keep = cv2.dilate(crop_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    crop[keep == 0] = 255
    region = find_green_board(image) | {"angle": round(float(angle), 1)}
    return "ok", BoardCrop(Image.fromarray(crop), region, crop_mask)


def share_inside(mask: np.ndarray, box: dict) -> float:
    """Fraction of a normalized box that lies on the board."""
    height, width = mask.shape
    left, top = max(0, int(box["x"] * width)), max(0, int(box["y"] * height))
    right, bottom = min(width, int(round((box["x"] + box["w"]) * width))), min(height, int(round((box["y"] + box["h"]) * height)))
    if right <= left or bottom <= top:
        return 0.0
    return float(np.count_nonzero(mask[top:bottom, left:right])) / ((right - left) * (bottom - top))
