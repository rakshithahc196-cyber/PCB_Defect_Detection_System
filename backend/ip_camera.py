"""Connect to a network camera from just its IP address and keep its latest JPEG frame."""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import URLError
from urllib.request import Request, urlopen

import cv2


# Common endpoints, tried in order: Android "IP Webcam", ESP32-CAM, generic MJPEG/snapshot cameras, then RTSP.
CANDIDATES = [
    ("http", 8080, "/video"), ("http", 8080, "/shot.jpg"),
    ("http", 81, "/stream"), ("http", 80, "/capture"),
    ("http", 80, "/video"), ("http", 80, "/mjpg/video.mjpg"), ("http", 80, "/video.mjpg"), ("http", 80, "/mjpeg"),
    ("http", 80, "/snapshot.jpg"), ("http", 80, "/image.jpg"), ("http", 80, "/cgi-bin/snapshot.cgi"), ("http", 80, "/jpg/image.jpg"),
    ("http", 8081, "/"), ("http", 8000, "/video"),
    ("rtsp", 554, "/"), ("rtsp", 554, "/stream1"), ("rtsp", 554, "/live"), ("rtsp", 554, "/h264"),
    ("rtsp", 554, "/live/ch00_0"), ("rtsp", 554, "/cam/realmonitor?channel=1&subtype=0"), ("rtsp", 8554, "/live"),
]
CONNECT_TIMEOUT = 2.0
FRAME_STALE_AFTER = 5.0
SNAPSHOT_INTERVAL = 0.2


class IpCameraError(Exception):
    """The address is invalid or no supported camera stream answered."""


def parse_address(address: str) -> tuple[str, int | None]:
    """Accept `192.168.1.20` or `192.168.1.20:8080` (IPv6 as `[fe80::1]:8080`); hostnames and URLs are rejected."""
    text = address.strip()
    if "://" in text or "/" in text or "@" in text:
        raise IpCameraError("Enter only the camera IP address, optionally with a port (for example 192.168.1.20:8080)")
    host, port = text, None
    if text.startswith("["):
        host, _, rest = text[1:].partition("]")
        if rest:
            if not rest.startswith(":"):
                raise IpCameraError("Enter a valid IP address")
            port = rest[1:]
    elif text.count(":") == 1:
        host, port = text.split(":")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        raise IpCameraError("Enter a valid IP address, for example 192.168.1.20") from exc
    if port is not None:
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise IpCameraError("Port must be a number from 1 to 65535")
        port = int(port)
    return (f"[{ip}]" if ip.version == 6 else str(ip)), port


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host.strip("[]"), port), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def candidate_urls(host: str, port: int | None) -> list[str]:
    if port is None:
        entries = CANDIDATES
    else:
        scheme = "rtsp" if port in (554, 8554) else "http"
        entries = [(scheme, port, path) for kind, _, path in CANDIDATES if kind == scheme]
        entries = list(dict.fromkeys(entries))
    ports = sorted({entry_port for _, entry_port, _ in entries})
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        open_ports = dict(zip(ports, pool.map(lambda entry_port: port_open(host, entry_port), ports)))
    return [f"{scheme}://{host}:{entry_port}{path}" for scheme, entry_port, path in entries if open_ports[entry_port]]


def read_mjpeg(response, stop: threading.Event):
    """Yield JPEG frames from a multipart MJPEG body by scanning for JPEG start/end markers."""
    buffer = b""
    while not stop.is_set():
        chunk = response.read(16384)
        if not chunk:
            return
        buffer += chunk
        start = buffer.find(b"\xff\xd8")
        end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
        while start >= 0 and end >= 0:
            yield buffer[start:end + 2]
            buffer = buffer[end + 2:]
            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
        if len(buffer) > 8 * 1024 * 1024:
            buffer = buffer[-1024 * 1024:]


def probe_http(url: str) -> str | None:
    """Return 'mjpeg' or 'snapshot' if the URL serves camera images."""
    try:
        with urlopen(Request(url, headers={"User-Agent": "pcb-vision"}), timeout=CONNECT_TIMEOUT) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "multipart" in content_type:
                return "mjpeg" if next(read_mjpeg(response, threading.Event()), None) else None
            if content_type.startswith("image/") and response.read(3) == b"\xff\xd8\xff":
                return "snapshot"
    except (URLError, OSError, ValueError):
        return None
    return None


def open_rtsp(url: str):
    capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000])
    if capture.isOpened() and capture.read()[0]:
        return capture
    capture.release()
    return None


class IpCamera:
    """A single shared network camera; a background thread keeps the newest frame."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.frame: bytes | None = None
        self.frame_at = 0.0
        self.address = ""
        self.url = ""
        self.kind = ""
        self.error = ""
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def connect(self, address: str) -> dict:
        host, port = parse_address(address)
        self.disconnect()
        urls = candidate_urls(host, port)
        if not urls:
            raise IpCameraError(f"No camera ports answered at {address.strip()}. Check the IP address and that the camera is on the same network.")
        for url in urls:
            kind = "rtsp" if url.startswith("rtsp://") else probe_http(url)
            capture = open_rtsp(url) if kind == "rtsp" else None
            if kind is None or (kind == "rtsp" and capture is None):
                continue
            stop = threading.Event()
            with self.lock:
                self.address, self.url, self.kind, self.error = address.strip(), url, kind, ""
                self.frame, self.frame_at, self.stop_event = None, 0.0, stop
            self.thread = threading.Thread(target=self.run, args=(url, kind, capture, stop), daemon=True, name="ip-camera")
            self.thread.start()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and self.latest() is None:
                time.sleep(0.05)
            if self.latest() is None:
                self.disconnect()
                continue
            return self.status()
        raise IpCameraError(f"Found a device at {address.strip()} but no supported video stream (MJPEG, JPEG snapshot or RTSP). Try adding the stream port, e.g. {host}:8080.")

    def run(self, url: str, kind: str, capture, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                if kind == "rtsp":
                    ok, frame = capture.read()
                    if not ok:
                        raise OSError("RTSP stream stopped")
                    self.store(cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes(), stop)
                elif kind == "mjpeg":
                    with urlopen(Request(url, headers={"User-Agent": "pcb-vision"}), timeout=CONNECT_TIMEOUT * 3) as response:
                        for jpeg in read_mjpeg(response, stop):
                            self.store(jpeg, stop)
                else:
                    with urlopen(Request(url, headers={"User-Agent": "pcb-vision"}), timeout=CONNECT_TIMEOUT * 3) as response:
                        self.store(response.read(), stop)
                    stop.wait(SNAPSHOT_INTERVAL)
            except (URLError, OSError, ValueError) as exc:
                with self.lock:
                    if self.stop_event is stop:
                        self.error = str(exc)
                if kind == "rtsp":
                    capture.release()
                    capture = None
                    while capture is None and not stop.wait(1):
                        capture = open_rtsp(url)
                else:
                    stop.wait(1)
        if capture is not None:
            capture.release()

    def store(self, jpeg: bytes, stop: threading.Event) -> None:
        with self.lock:
            if self.stop_event is stop and jpeg[:2] == b"\xff\xd8":
                self.frame, self.frame_at, self.error = jpeg, time.monotonic(), ""

    def latest(self) -> bytes | None:
        with self.lock:
            if self.frame is None or time.monotonic() - self.frame_at > FRAME_STALE_AFTER:
                return None
            return self.frame

    def disconnect(self) -> None:
        with self.lock:
            self.stop_event.set()
            self.frame, self.address, self.url, self.kind, self.error = None, "", "", "", ""
        self.thread = None

    def status(self) -> dict:
        with self.lock:
            live = self.frame is not None and time.monotonic() - self.frame_at <= FRAME_STALE_AFTER
            return {"connected": bool(self.url), "live": live, "address": self.address, "kind": self.kind, "source": self.url, "error": self.error}
