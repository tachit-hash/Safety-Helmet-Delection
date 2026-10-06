import os
import csv
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from src.config import MODEL_PATH
from src.config import SCAN_INTERVAL_SECONDS
from src.association import AssociationEngine
from src.detector import HelmetDetector
from src.logger import ViolationLogger
from src.pipeline import DetectionPipeline
from src.tracker import ObjectTracker
from src.web_service import _draw_status_marker
from src.web_service import ScanService
from app import app


class TestHelmetDetection(unittest.TestCase):
    def test_model_file_exists(self):
        """Verify the YOLO model file exists."""
        self.assertTrue(os.path.exists(MODEL_PATH), f"Model file not found at {MODEL_PATH}")

    def test_person_track_keeps_id_between_frames(self):
        """A person moving slightly between frames keeps the same track ID."""
        tracker = ObjectTracker()
        first = tracker.update({
            "persons": [{"bbox": [10, 10, 50, 100], "conf": 0.9}],
            "helmets": [],
            "no_helmets": [],
        })
        second = tracker.update({
            "persons": [{"bbox": [12, 10, 52, 100], "conf": 0.9}],
            "helmets": [],
            "no_helmets": [],
        })
        self.assertEqual(first["persons"][0]["track_id"], second["persons"][0]["track_id"])

    def test_person_without_helmet_in_head_area_is_no_helmet(self):
        """An explicitly detected uncovered head is non-compliant."""
        result = AssociationEngine().associate_and_classify({
            "persons": [{"bbox": [0, 0, 100, 200], "conf": 0.99}],
            "helmets": [],
            "no_helmets": [{"bbox": [20, 10, 60, 45], "conf": 0.95}],
        })
        self.assertEqual(result[0]["status"], "NO HELMET")

    def test_person_without_head_status_detection_is_unknown(self):
        """A person is not marked unsafe when the head status is not detected."""
        result = AssociationEngine().associate_and_classify({
            "persons": [{"bbox": [0, 0, 100, 200], "conf": 0.99}],
            "helmets": [],
            "no_helmets": [],
        })
        self.assertEqual(result[0]["status"], "UNKNOWN")

    def test_helmet_in_head_area_is_compliant(self):
        """A helmet overlapping the head area produces a helmet status."""
        result = AssociationEngine().associate_and_classify({
            "persons": [{"bbox": [0, 0, 100, 200], "conf": 0.99}],
            "helmets": [{"bbox": [20, 10, 60, 45], "conf": 0.95}],
            "no_helmets": [],
        })
        self.assertEqual(result[0]["status"], "HELMET")

    def test_model_without_helmet_classes_keeps_status_unknown(self):
        """Without a helmet model, colored headwear is classified locally."""
        pipeline = DetectionPipeline.__new__(DetectionPipeline)
        pipeline.detector = Mock()
        pipeline.detector.helmet_detection_available = False
        pipeline.detector.has_colored_headgear.return_value = True
        pipeline.detector.detect.return_value = {
            "persons": [{"bbox": [0, 0, 100, 200], "conf": 0.99}],
            "helmets": [],
            "no_helmets": [],
        }
        pipeline.tracker = Mock()
        pipeline.tracker.update.side_effect = lambda detections: detections
        pipeline.associator = Mock()
        pipeline.associator.associate_and_classify.return_value = [{
            "bbox": [0, 0, 100, 200],
            "conf": 0.99,
            "status": "NO HELMET",
        }]

        result = pipeline.process_frame(np.zeros((200, 100, 3), dtype=np.uint8))

        self.assertEqual(result[0]["status"], "HELMET")

    def test_helmet_color_is_not_shared_between_overlapping_people(self):
        """A neighboring person's colored headgear cannot classify this person."""
        frame = np.zeros((240, 180, 3), dtype=np.uint8)
        frame[52:81, 62:98] = (255, 0, 0)
        face_cascade = Mock()
        face_cascade.detectMultiScale.return_value = np.array([[30, 70, 50, 60]])

        with patch("src.detector._face_cascade", return_value=face_cascade):
            self.assertTrue(
                HelmetDetector.has_colored_headgear(frame, [10, 10, 110, 230])
            )
            self.assertFalse(
                HelmetDetector.has_colored_headgear(
                    frame,
                    [10, 10, 110, 230],
                    [(70, 10, 170, 230)],
                )
            )

    def test_pipeline_checks_each_person_without_borrowing_neighbor_area(self):
        pipeline = DetectionPipeline.__new__(DetectionPipeline)
        pipeline.detector = Mock()
        pipeline.detector.helmet_detection_available = False
        pipeline.detector.has_colored_headgear.side_effect = [True, False]
        pipeline.detector.detect.return_value = {
            "persons": [
                {"bbox": [0, 0, 100, 200], "conf": 0.99},
                {"bbox": [80, 0, 180, 200], "conf": 0.99},
            ],
            "helmets": [],
            "no_helmets": [],
        }
        pipeline.tracker = Mock()
        pipeline.tracker.update.side_effect = lambda detections: detections
        pipeline.associator = Mock()
        pipeline.associator.associate_and_classify.return_value = [
            {"bbox": [0, 0, 100, 200], "conf": 0.99, "status": "NO HELMET"},
            {"bbox": [80, 0, 180, 200], "conf": 0.99, "status": "NO HELMET"},
        ]

        result = pipeline.process_frame(np.zeros((200, 180, 3), dtype=np.uint8))

        self.assertEqual(
            [person["status"] for person in result],
            ["HELMET", "NO HELMET"],
        )
        self.assertEqual(
            pipeline.detector.has_colored_headgear.call_args_list[0].args[2],
            [[80, 0, 180, 200]],
        )
        self.assertEqual(
            pipeline.detector.has_colored_headgear.call_args_list[1].args[2],
            [[0, 0, 100, 200]],
        )

    def test_colored_headgear_heuristic(self):
        """Supported helmet colors above a detected face are recognized."""
        helmet_colors = (
            (255, 0, 0),
            (0, 255, 255),
            (0, 0, 255),
            (255, 0, 255),
            (128, 0, 128),
            (255, 255, 255),
        )
        face_cascade = Mock()
        face_cascade.detectMultiScale.return_value = np.array([[35, 70, 50, 60]])
        with patch("src.detector._face_cascade", return_value=face_cascade):
            for color in helmet_colors:
                with self.subTest(color=color):
                    frame = np.zeros((240, 160, 3), dtype=np.uint8)
                    frame[52:81, 62:98] = color
                    self.assertTrue(
                        HelmetDetector.has_colored_headgear(frame, [20, 10, 140, 230])
                    )

            no_helmet_frame = np.zeros((240, 160, 3), dtype=np.uint8)
            no_helmet_frame[35:75, 20:35] = (180, 0, 255)
            no_helmet_frame[35:75, 85:100] = (180, 0, 255)
            self.assertFalse(
                HelmetDetector.has_colored_headgear(
                    no_helmet_frame,
                    [20, 10, 140, 230],
                )
            )
            self.assertTrue(all(
                call.kwargs["scaleFactor"] == 1.05
                and call.kwargs["minNeighbors"] == 3
                for call in face_cascade.detectMultiScale.call_args_list
            ))

        face_cascade.detectMultiScale.return_value = np.empty((0, 4), dtype=int)
        with patch("src.detector._face_cascade", return_value=face_cascade):
            self.assertFalse(
                HelmetDetector.has_colored_headgear(
                    np.full((240, 160, 3), (180, 0, 255), dtype=np.uint8),
                    [20, 10, 140, 230],
                )
            )

    def test_event_saves_image_and_percentages(self):
        """An event is saved with its timestamp, image, and helmet percentages."""
        stats = {
            "total_people": 2,
            "helmet_count": 1,
            "no_helmet_count": 1,
            "unknown_count": 0,
            "helmet_percent": 50.0,
            "no_helmet_percent": 50.0,
        }
        with tempfile.TemporaryDirectory() as output_dir:
            logger = ViolationLogger(output_dir=output_dir)
            logger.log_event(
                np.zeros((20, 20, 3), dtype=np.uint8),
                "NO HELMET",
                stats,
                confidence=0.873,
            )

            with open(logger.csv_file, newline="", encoding="utf-8-sig") as file:
                row = next(csv.DictReader(file))

            self.assertEqual(row["Status"], "NO HELMET")
            self.assertEqual(row["No_Helmet_Percent"], "50.0")
            self.assertEqual(row["Confidence"], "0.8730")
            self.assertTrue(os.path.exists(row["Image_Path"]))

    def test_detector_can_be_imported(self):
        """Ensure the detector class is available for runtime use."""
        self.assertIsNotNone(HelmetDetector)

    def test_dashboard_and_history_api_are_available(self):
        """The browser dashboard and saved scan history are accessible."""
        client = app.test_client()
        dashboard_response = client.get("/")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_html = dashboard_response.get_data(as_text=True)
        self.assertIn('<html lang="en">', dashboard_html)
        self.assertNotRegex(dashboard_html, r"[\u1780-\u17FF]")
        self.assertIn(b"helmet-example.png", dashboard_response.data)
        self.assertIn(b"no-helmet-example.png", dashboard_response.data)
        for view in (
            "dashboard",
            "live",
            "cameras",
            "videos",
            "history",
            "reports",
            "users",
            "settings",
        ):
            self.assertIn(f'id="view-{view}"'.encode(), dashboard_response.data)
        self.assertIn(b'id="detection-count"', dashboard_response.data)
        self.assertIn(b'id="overview-chart"', dashboard_response.data)
        self.assertIn(b'id="overview-total"', dashboard_response.data)
        self.assertIn(b'id="overview-cameras"', dashboard_response.data)
        self.assertIn(b'id="page-subtitle"', dashboard_response.data)
        self.assertIn(b'id="notification-toggle"', dashboard_response.data)
        self.assertIn(b'id="notification-menu"', dashboard_response.data)
        self.assertIn(b'id="profile-toggle"', dashboard_response.data)
        self.assertIn(b'id="air-pointer-toggle"', dashboard_response.data)
        self.assertIn(b'id="air-pointer-video"', dashboard_response.data)
        self.assertIn(b"Camera video is processed locally and is not uploaded.", dashboard_response.data)
        self.assertIn(b"Admin", dashboard_response.data)
        self.assertIn(b'id="report-start-date"', dashboard_response.data)
        self.assertIn(b'id="report-end-date"', dashboard_response.data)
        self.assertIn(b'id="report-trend-chart"', dashboard_response.data)
        self.assertIn(b'id="report-ratio-chart"', dashboard_response.data)
        helmet_image_response = client.get("/static/images/helmet-example.png")
        self.assertEqual(helmet_image_response.status_code, 200)
        helmet_image_response.close()
        no_helmet_image_response = client.get("/static/images/no-helmet-example.png")
        self.assertEqual(no_helmet_image_response.status_code, 200)
        no_helmet_image_response.close()
        pointer_script_response = client.get("/static/air_pointer.js")
        self.assertEqual(pointer_script_response.status_code, 200)
        pointer_script_response.close()
        vision_asset_response = client.get("/vendor/mediapipe/vision_bundle.mjs")
        self.assertEqual(vision_asset_response.status_code, 200)
        vision_asset_response.close()
        vision_wasm_response = client.get("/vendor/mediapipe/wasm/vision_wasm_internal.wasm")
        self.assertEqual(vision_wasm_response.status_code, 200)
        vision_wasm_response.close()
        blocked_vision_asset_response = client.get("/vendor/mediapipe/README.md")
        self.assertEqual(blocked_vision_asset_response.status_code, 404)
        blocked_vision_asset_response.close()
        history_response = client.get("/api/history")
        self.assertEqual(history_response.status_code, 200)
        self.assertIsInstance(history_response.get_json(), list)

    def test_scan_interval_is_ten_seconds(self):
        """The configured camera inference interval is ten seconds."""
        self.assertEqual(SCAN_INTERVAL_SECONDS, 10)

    def test_scan_overlay_draws_user_requested_red_cross(self):
        """The no-helmet scan result displays a bold red cross."""
        helmet_frame = np.zeros((80, 100, 3), dtype=np.uint8)
        no_helmet_frame = np.zeros((80, 100, 3), dtype=np.uint8)
        unknown_frame = np.zeros((80, 100, 3), dtype=np.uint8)
        bbox = [10, 10, 70, 70]

        _draw_status_marker(helmet_frame, bbox, "HELMET")
        _draw_status_marker(no_helmet_frame, bbox, "NO HELMET")
        _draw_status_marker(unknown_frame, bbox, "UNKNOWN")

        helmet_color = helmet_frame[16, 56]
        no_helmet_color = no_helmet_frame[15, 47]
        no_helmet_other_stroke = no_helmet_frame[33, 47]
        unknown_color = unknown_frame[16, 56]
        self.assertGreater(int(helmet_color[1]), int(helmet_color[0]))
        self.assertGreater(int(helmet_color[1]), int(helmet_color[2]))
        self.assertGreater(int(no_helmet_color[2]), int(no_helmet_color[1]))
        self.assertGreater(int(no_helmet_other_stroke[2]), int(no_helmet_other_stroke[1]))
        self.assertGreater(int(unknown_color[2]), int(unknown_color[1]))

    def test_new_detection_event_is_exposed_for_dashboard_popup(self):
        """A newly scanned person produces a unique event for the live dashboard."""
        service = ScanService()
        stats = {
            "total_people": 1,
            "helmet_count": 0,
            "no_helmet_count": 0,
            "unknown_count": 1,
        }
        service._publish_detection_event([{"status": "UNKNOWN"}], stats)
        state = service.status()
        self.assertEqual(state["event_id"], 1)
        self.assertEqual(state["last_detection_event"]["statuses"], ["UNKNOWN"])
        self.assertEqual(state["last_detection_event"]["unknown_count"], 1)

    def test_saved_scan_image_is_served_from_storage(self):
        """Saved scan images can be viewed from the dashboard."""
        with tempfile.TemporaryDirectory() as output_dir:
            logger = ViolationLogger(output_dir=output_dir)
            stats = {
                "total_people": 1,
                "helmet_count": 0,
                "no_helmet_count": 0,
                "unknown_count": 1,
                "helmet_percent": 0.0,
                "no_helmet_percent": 0.0,
            }
            logger.log_event(
                np.zeros((20, 20, 3), dtype=np.uint8),
                "UNKNOWN",
                stats,
                confidence=0.93,
            )
            with open(logger.csv_file, newline="", encoding="utf-8-sig") as file:
                image_name = os.path.basename(next(csv.DictReader(file))["Image_Path"])
            with patch("app.event_logger", logger):
                client = app.test_client()
                response = client.get(f"/scans/{image_name}")
                self.assertEqual(response.status_code, 200)
                response.close()
                detail = client.get(f"/api/history/{image_name}")

            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.get_json()["Confidence"], "0.9300")
            self.assertEqual(detail.get_json()["Image_Name"], image_name)

    def test_delete_scan_removes_its_image_and_record_only(self):
        """Deleting one history item removes its image without affecting others."""
        stats = {
            "total_people": 1,
            "helmet_count": 0,
            "no_helmet_count": 0,
            "unknown_count": 1,
            "helmet_percent": 0.0,
            "no_helmet_percent": 0.0,
        }
        with tempfile.TemporaryDirectory() as output_dir:
            logger = ViolationLogger(output_dir=output_dir)
            logger.log_event(np.zeros((20, 20, 3), dtype=np.uint8), "UNKNOWN", stats)
            logger.log_event(np.ones((20, 20, 3), dtype=np.uint8), "UNKNOWN", stats)
            with open(logger.csv_file, newline="", encoding="utf-8-sig") as file:
                rows = list(csv.DictReader(file))
            deleted_image = rows[0]["Image_Path"]
            retained_image = rows[1]["Image_Path"]
            image_name = os.path.basename(deleted_image)

            with patch("app.event_logger", logger):
                response = app.test_client().post(f"/api/history/{image_name}/delete")
                remaining = app.test_client().get("/api/history").get_json()

            self.assertEqual(response.status_code, 200)
            self.assertFalse(os.path.exists(deleted_image))
            self.assertTrue(os.path.exists(retained_image))
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0]["Image_Name"], os.path.basename(retained_image))

    def test_delete_scan_rejects_invalid_filename(self):
        """History deletion does not allow paths outside the scan storage."""
        response = app.test_client().post("/api/history/..%5Csecret.jpg/delete")
        self.assertIn(response.status_code, (400, 404))


if __name__ == "__main__":
    unittest.main()