import os
from functools import lru_cache

import cv2

try:
    from ultralytics import YOLO
except ImportError:  
    YOLO = None

from src.config import MODEL_PATH, CONFIDENCE_THRESHOLD


@lru_cache(maxsize=1)
def _face_cascade():
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if cascade.empty():
        raise RuntimeError("Unable to load the OpenCV face detector.")
    return cascade


class HelmetDetector:
    def __init__(self, model_path=MODEL_PATH, conf_thresh=CONFIDENCE_THRESHOLD):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found at {model_path}")

        if YOLO is None:
            raise ImportError("ultralytics is required to run HelmetDetector. Install it with 'pip install ultralytics'.")

        print(f"Loading YOLO model from: {model_path}")
        self.model = YOLO(model_path)
        self.conf_thresh = conf_thresh
        helmet_labels = {
            "helmet",
            "hard_hat",
            "safety_helmet",
            "hat",
            "cap",
            "hardhat",
            "no_helmet",
            "head",
            "head_without_helmet",
            "unhelmeted",
            "without_helmet",
        }
        class_names = getattr(self.model, "names", {})
        available_class_names = class_names.values() if isinstance(class_names, dict) else class_names
        normalized_class_names = {
            str(name).lower().replace("-", "_").replace(" ", "_")
            for name in available_class_names
        }
        self.helmet_detection_available = bool(
            normalized_class_names.intersection(helmet_labels)
        )

    @staticmethod
    def has_colored_headgear(frame, person_bbox, other_person_bboxes=()):
        """Check helmet colors only in the strip immediately above a detected face."""
        frame_height, frame_width = frame.shape[:2]
        x1, y1, x2, y2 = map(int, person_bbox)
        person_width = x2 - x1
        person_height = y2 - y1
        if person_width < 2 or person_height < 2:
            return False

        person_region = frame[
            max(0, y1):min(frame_height, y2),
            max(0, x1):min(frame_width, x2),
        ]
        if person_region.size == 0:
            return False

        person_gray = cv2.cvtColor(person_region, cv2.COLOR_BGR2GRAY)
        face_boxes = _face_cascade().detectMultiScale(
            person_gray[:max(1, int(person_height * 0.8))],
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(max(24, int(person_width * 0.14)), max(24, int(person_height * 0.08))),
        )
        if len(face_boxes) == 0:
            return False

        face_x, face_y, face_width, face_height = max(
            face_boxes,
            key=lambda box: int(box[2]) * int(box[3]),
        )
        left = max(0, int(face_x + face_width * 0.08))
        right = min(person_region.shape[1], int(face_x + face_width * 0.92))
        top = max(0, int(face_y - face_height * 0.5))
        bottom = min(person_region.shape[0], int(face_y + face_height * 0.05))
        head_region = person_region[top:bottom, left:right]
        if head_region.size == 0:
            return False

        hsv_region = cv2.cvtColor(head_region, cv2.COLOR_BGR2HSV)
        color_masks = [
            cv2.inRange(hsv_region, (0, 120, 45), (12, 255, 255)),
            cv2.inRange(hsv_region, (168, 120, 45), (179, 255, 255)),
            cv2.inRange(hsv_region, (18, 100, 65), (38, 255, 255)),
            cv2.inRange(hsv_region, (85, 70, 45), (135, 255, 255)),
            cv2.inRange(hsv_region, (136, 65, 55), (167, 255, 255)),
            cv2.inRange(hsv_region, (0, 0, 190), (179, 55, 255)),
        ]
        headgear_mask = cv2.bitwise_or(color_masks[0], color_masks[1])
        for color_mask in color_masks[2:]:
            headgear_mask = cv2.bitwise_or(headgear_mask, color_mask)
        headgear_mask = cv2.morphologyEx(
            headgear_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        )
        ownership_mask = headgear_mask.copy()
        head_left = max(0, x1) + left
        head_top = max(0, y1) + top
        for other_bbox in other_person_bboxes:
            other_x1, other_y1, other_x2, other_y2 = map(int, other_bbox)
            overlap_left = max(head_left, other_x1)
            overlap_top = max(head_top, other_y1)
            overlap_right = min(head_left + head_region.shape[1], other_x2)
            overlap_bottom = min(head_top + head_region.shape[0], other_y2)
            if overlap_left < overlap_right and overlap_top < overlap_bottom:
                ownership_mask[
                    overlap_top - head_top:overlap_bottom - head_top,
                    overlap_left - head_left:overlap_right - head_left,
                ] = 0
        headgear_mask = cv2.bitwise_and(headgear_mask, ownership_mask)
        contours, _ = cv2.findContours(
            headgear_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        minimum_area = max(50, int(head_region.shape[0] * head_region.shape[1] * 0.12))
        minimum_width = face_width * 0.45
        return any(
            cv2.contourArea(contour) >= minimum_area
            and cv2.boundingRect(contour)[2] >= minimum_width
            for contour in contours
        )

    def _class_name(self, cls_id):
        names = getattr(self.model, "names", {})
        if isinstance(names, dict):
            return str(names.get(cls_id, cls_id)).lower()
        if isinstance(names, list) and cls_id < len(names):
            return str(names[cls_id]).lower()
        return str(cls_id).lower()

    def detect(self, frame):
        """
        Run object detection on the frame.
        Returns a dictionary separating persons, helmets, and no_helmets.
        """
        results = self.model(frame, conf=self.conf_thresh, verbose=False)[0]
        detections = {
            "persons": [],
            "helmets": [],
            "no_helmets": []
        }
        person_labels = {"person", "people", "man", "woman"}
        helmet_labels = {
            "helmet",
            "hard_hat",
            "safety_helmet",
            "hat",
            "cap",
            "hardhat",
        }
        no_helmet_labels = {
            "no_helmet",
            "head",
            "head_without_helmet",
            "unhelmeted",
            "without_helmet",
        }
        for box in results.boxes:
            cls_id = int(box.cls[0])
            class_name = self._class_name(cls_id).replace("-", "_").replace(" ", "_")
            conf = float(box.conf[0])
            xyxy = box.xyxy[0].cpu().numpy().astype(int).tolist()
            item = {"bbox": xyxy, "conf": conf}

            if class_name in person_labels:
                detections["persons"].append(item)
            elif class_name in helmet_labels:
                detections["helmets"].append(item)
            elif class_name in no_helmet_labels:
                detections["no_helmets"].append(item)

        return detections
