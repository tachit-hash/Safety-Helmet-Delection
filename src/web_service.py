import threading
import math
import time

import cv2

from src.config import (
    COLOR_HELMET,
    COLOR_NO_HELMET,
    COLOR_UNKNOWN,
    SCAN_INTERVAL_SECONDS,
    get_camera_stream,
)
from src.logger import ViolationLogger


def _draw_status_marker(frame, bbox, status):
    if status not in {"HELMET", "NO HELMET", "UNKNOWN"}:
        return

    height, width = frame.shape[:2]
    x1, y1, x2, y2 = map(int, bbox)
    center = (
        min(max(x2 - 14, 16), width - 16),
        min(max(y1 + 14, 16), height - 16),
    )
    color = (
        COLOR_HELMET if status == "HELMET"
        else COLOR_NO_HELMET if status == "NO HELMET"
        else (0, 165, 255)
    )
    if status == "NO HELMET":
        marker_size = max(8, min(15, min(height, width) // 8))
        thickness = max(4, marker_size // 2)
        cv2.line(
            frame,
            (center[0] - marker_size, center[1] - marker_size),
            (center[0] + marker_size, center[1] + marker_size),
            color,
            thickness,
            cv2.LINE_AA,
        )
        cv2.line(
            frame,
            (center[0] - marker_size, center[1] + marker_size),
            (center[0] + marker_size, center[1] - marker_size),
            color,
            thickness,
            cv2.LINE_AA,
        )
        bbox_width = max(1, x2 - x1)
        font_scale = min(3.0, max(0.7, (bbox_width - 16) / 48))
        font_thickness = max(2, int(font_scale * 3))
        (text_width, text_height), baseline = cv2.getTextSize(
            "NO",
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            font_thickness,
        )
        text_x = min(max(0, x1 + 8), max(0, width - text_width - 2))
        text_y = min(max(text_height + 2, y2 - 12), height - baseline - 2)
        text_y = max(text_height + 2, text_y)
        cv2.putText(
            frame,
            "NO",
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            font_thickness + 4,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            "NO",
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            font_thickness,
            cv2.LINE_AA,
        )
    else:
        cv2.circle(frame, center, 13, color, -1, cv2.LINE_AA)
        cv2.circle(frame, center, 13, (255, 255, 255), 1, cv2.LINE_AA)
    if status == "HELMET":
        cv2.line(
            frame,
            (center[0] - 6, center[1]),
            (center[0] - 2, center[1] + 4),
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.line(
            frame,
            (center[0] - 2, center[1] + 4),
            (center[0] + 6, center[1] - 5),
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.putText(
            frame,
            "?",
            (center[0] - 5, center[1] + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.line(
            frame,
            (center[0] + 5, center[1] - 5),
            (center[0] - 5, center[1] + 5),
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )


class ScanService:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._latest_jpeg = None
        self._state = {
            "running": False,
            "error": "",
            "warning": "",
            "total_people": 0,
            "helmet_count": 0,
            "no_helmet_count": 0,
            "unknown_count": 0,
            "helmet_percent": 0.0,
            "no_helmet_percent": 0.0,
            "scan_interval_seconds": SCAN_INTERVAL_SECONDS,
            "next_scan_in": 0,
            "event_id": 0,
            "last_detection_event": None,
        }

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._state.update(running=True, error="", warning="")
            self._thread = threading.Thread(target=self._scan, daemon=True)
            self._thread.start()
            return True

    def stop(self):
        self._stop_event.set()
        return self.status()

    def status(self):
        with self._lock:
            return dict(self._state)

    def latest_jpeg(self):
        with self._lock:
            return self._latest_jpeg

    def wait_for_frame(self, seconds):
        self._stop_event.wait(seconds)

    def _set_state(self, **changes):
        with self._lock:
            self._state.update(changes)

    def _publish_detection_event(self, detections, stats):
        with self._lock:
            self._state["event_id"] += 1
            self._state["last_detection_event"] = {
                "id": self._state["event_id"],
                "statuses": [detection["status"] for detection in detections],
                "total_people": stats["total_people"],
                "helmet_count": stats["helmet_count"],
                "no_helmet_count": stats["no_helmet_count"],
                "unknown_count": stats["unknown_count"],
            }

    def _scan(self):
        camera = None
        inference_thread = None
        inference_requested = threading.Event()
        inference_lock = threading.Lock()
        latest_inference_frame = None
        inference_result = {
            "people": [],
            "stats": {
                "total_people": 0,
                "helmet_count": 0,
                "no_helmet_count": 0,
                "unknown_count": 0,
                "helmet_percent": 0.0,
                "no_helmet_percent": 0.0,
            },
            "error": None,
        }
        try:
            from src.pipeline import DetectionPipeline

            pipeline = DetectionPipeline()
            logger = ViolationLogger()

            class_names = pipeline.detector.model.names
            names = class_names.values() if isinstance(class_names, dict) else class_names
            normalized_names = {
                str(name).lower().replace("-", "_").replace(" ", "_")
                for name in names
            }
            helmet_labels = {"helmet", "hard_hat", "safety_helmet", "hat", "cap", "hardhat"}
            no_helmet_labels = {
                "no_helmet",
                "head",
                "head_without_helmet",
                "unhelmeted",
                "without_helmet",
            }
            warning = ""
            if not normalized_names.intersection(helmet_labels | no_helmet_labels):
                warning = (
                    "Warning: The current model cannot identify safety helmets. "
                    "It checks for blue, yellow, red, pink, purple, or white color in the upper head "
                    "area; this may mistake similar background colors for headwear. "
                    "Set src/config.py to use a model trained for helmet detection."
                )
            self._set_state(warning=warning)

            camera = get_camera_stream(0)
            if camera is None or not camera.isOpened():
                raise RuntimeError("Unable to open the camera. Check the camera and try again.")

            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            camera.set(cv2.CAP_PROP_FPS, 20)
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            def run_inference():
                nonlocal latest_inference_frame
                while not self._stop_event.is_set():
                    inference_requested.wait()
                    inference_requested.clear()
                    if self._stop_event.is_set():
                        return
                    with inference_lock:
                        inference_frame = latest_inference_frame
                        latest_inference_frame = None
                    if inference_frame is None:
                        continue

                    try:
                        people = pipeline.process_frame(inference_frame)
                        total = len(people)
                        helmet_count = sum(person["status"] == "HELMET" for person in people)
                        no_helmet_count = sum(person["status"] == "NO HELMET" for person in people)
                        unknown_count = sum(person["status"] == "UNKNOWN" for person in people)
                        stats = {
                            "total_people": total,
                            "helmet_count": helmet_count,
                            "no_helmet_count": no_helmet_count,
                            "unknown_count": unknown_count,
                            "helmet_percent": helmet_count / total * 100 if total else 0.0,
                            "no_helmet_percent": no_helmet_count / total * 100 if total else 0.0,
                        }
                        with inference_lock:
                            inference_result.update(people=people, stats=stats)
                    except Exception as error:
                        with inference_lock:
                            inference_result["error"] = str(error)
                        return

            inference_thread = threading.Thread(target=run_inference, daemon=True)
            inference_thread.start()
            people = []
            stats = inference_result["stats"]
            next_scan_at = time.monotonic()
            next_frame_at = next_scan_at
            while not self._stop_event.is_set():
                ok, frame = camera.read()
                if not ok or frame is None:
                    raise RuntimeError("Unable to receive an image from the camera.")

                now = time.monotonic()
                if now >= next_scan_at:
                    with inference_lock:
                        latest_inference_frame = frame.copy()
                    inference_requested.set()
                    next_scan_at = now + SCAN_INTERVAL_SECONDS

                with inference_lock:
                    inference_error = inference_result["error"]
                    people = inference_result["people"]
                    stats = inference_result["stats"]
                if inference_error:
                    raise RuntimeError(f"Unable to process the camera image: {inference_error}")

                newly_detected = []
                for person in people:
                    x1, y1, x2, y2 = map(int, person["bbox"])
                    status = person["status"]
                    color = (
                        COLOR_HELMET if status == "HELMET"
                        else COLOR_NO_HELMET if status == "NO HELMET"
                        else COLOR_UNKNOWN
                    )
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        frame,
                        f"{status} {person['conf']:.2f}",
                        (x1, max(20, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2,
                    )
                    _draw_status_marker(frame, person["bbox"], status)

                    track_id = person.get("track_id")
                    if track_id is None or pipeline.tracker.is_announced(track_id, status):
                        continue
                    pipeline.tracker.mark_announced(track_id, status)
                    newly_detected.append({
                        "status": status,
                        "confidence": person["conf"],
                    })

                counter_overlay = frame.copy()
                cv2.rectangle(counter_overlay, (10, 10), (390, 132), (12, 25, 43), -1)
                cv2.addWeighted(counter_overlay, 0.78, frame, 0.22, 0, frame)
                counter_lines = [
                    f"People: {stats['total_people']}",
                    f"With helmet: {stats['helmet_count']} ({stats['helmet_percent']:.1f}%)",
                    f"No helmet: {stats['no_helmet_count']} ({stats['no_helmet_percent']:.1f}%)",
                    f"Unknown: {stats['unknown_count']}",
                ]
                for line_number, text in enumerate(counter_lines):
                    cv2.putText(
                        frame,
                        text,
                        (22, 36 + line_number * 27),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.62,
                        (255, 255, 255),
                        2,
                    )

                for detection in newly_detected:
                    logger.log_event(
                        frame,
                        detection["status"],
                        stats,
                        confidence=detection["confidence"],
                    )
                if newly_detected:
                    self._publish_detection_event(newly_detected, stats)

                self._set_state(
                    next_scan_in=max(0, math.ceil(next_scan_at - now))
                )

                encoded, buffer = cv2.imencode(
                    ".jpg",
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 80],
                )
                if encoded:
                    with self._lock:
                        self._latest_jpeg = buffer.tobytes()
                        self._state.update(stats)

                next_frame_at += 1 / 20
                delay = next_frame_at - time.monotonic()
                if delay > 0:
                    self._stop_event.wait(delay)
                else:
                    next_frame_at = time.monotonic()

        except Exception as error:
            self._set_state(error=str(error))
        finally:
            self._stop_event.set()
            inference_requested.set()
            if inference_thread and inference_thread.is_alive():
                inference_thread.join(timeout=1)
            if camera is not None:
                camera.release()
            self._set_state(running=False)
