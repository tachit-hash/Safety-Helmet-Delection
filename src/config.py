import os
import cv2

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIDENCE_THRESHOLD = 0.5
ALERT_FRAME_THRESHOLD = 15
SCAN_INTERVAL_SECONDS = 10
MODEL_PATH = os.path.join(ROOT_DIR, "models", "yolov8n.pt")

COLOR_HELMET = (0, 255, 0)     
COLOR_NO_HELMET = (0, 0, 255)   
COLOR_UNKNOWN = (255, 255, 255) 


def get_camera_stream(source=0):
    """
    Phase 10: Input Source & Camera Manager
    Supports webcam index (int), video file path (str), or RTSP stream.
    """
    if isinstance(source, int):
        cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        print(f"[Error] Cannot open video source: {source}")
    return cap
