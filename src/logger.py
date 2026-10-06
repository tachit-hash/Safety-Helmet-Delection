import csv
import os
import time
from datetime import datetime

import cv2

from src.config import ROOT_DIR


class ViolationLogger:
    CSV_COLUMNS = [
        "Timestamp",
        "Image_Path",
        "Status",
        "Total_People",
        "Helmet_Count",
        "No_Helmet_Count",
        "Unknown_Count",
        "Helmet_Percent",
        "No_Helmet_Percent",
        "Confidence",
    ]

    def __init__(self, output_dir=None, cooldown_seconds=3):
        self.output_dir = output_dir or os.path.join(ROOT_DIR, "violations")
        self.cooldown_seconds = cooldown_seconds
        self.last_saved_time = 0
        os.makedirs(self.output_dir, exist_ok=True)
        self.csv_file = os.path.join(self.output_dir, "violations_log.csv")
        self._prepare_csv()

    def _prepare_csv(self):
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, "w", newline="", encoding="utf-8-sig") as file:
                csv.writer(file).writerow(self.CSV_COLUMNS)
            return

        with open(self.csv_file, "r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            old_columns = reader.fieldnames or []
            if all(column in old_columns for column in self.CSV_COLUMNS):
                return
            old_rows = list(reader)

        with open(self.csv_file, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=self.CSV_COLUMNS,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(old_rows)

    def log_event(self, frame, status, stats, confidence=None):
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        filename = now.strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
        filepath = os.path.join(self.output_dir, filename)

        if not cv2.imwrite(filepath, frame):
            raise OSError(f"Failed to save detection image: {filepath}")

        row = {
            "Timestamp": timestamp,
            "Image_Path": filepath,
            "Status": status,
            "Total_People": stats["total_people"],
            "Helmet_Count": stats["helmet_count"],
            "No_Helmet_Count": stats["no_helmet_count"],
            "Unknown_Count": stats["unknown_count"],
            "Helmet_Percent": f"{stats['helmet_percent']:.1f}",
            "No_Helmet_Percent": f"{stats['no_helmet_percent']:.1f}",
            "Confidence": "" if confidence is None else f"{confidence:.4f}",
        }
        with open(self.csv_file, "a", newline="", encoding="utf-8") as file:
            csv.DictWriter(file, fieldnames=self.CSV_COLUMNS).writerow(row)

        print(f"[LOG] Saved {status} event: {timestamp} -> {filepath}")

    def log_violation(self, frame, detection):
        status = detection.get("status", detection.get("label", "NO HELMET"))
        stats = self._empty_stats()
        stats["total_people"] = 1
        if status == "HELMET":
            stats["helmet_count"] = 1
            stats["helmet_percent"] = 100.0
        elif status == "NO HELMET":
            stats["no_helmet_count"] = 1
            stats["no_helmet_percent"] = 100.0
        else:
            stats["unknown_count"] = 1
        self.log_event(frame, status, stats)

    def log_detection(self, frame, person_results, is_alerting):
        if not is_alerting:
            return
        stats = self._stats(person_results)
        self.trigger_alert(frame, stats)

    def trigger_alert(self, frame, stats=None):
        current_time = time.time()
        if current_time - self.last_saved_time < self.cooldown_seconds:
            return
        self.last_saved_time = current_time
        self.log_event(frame, "NO HELMET", stats or self._empty_stats())

    @staticmethod
    def _empty_stats():
        return {
            "total_people": 0,
            "helmet_count": 0,
            "no_helmet_count": 0,
            "unknown_count": 0,
            "helmet_percent": 0.0,
            "no_helmet_percent": 0.0,
        }

    @classmethod
    def _stats(cls, people):
        stats = cls._empty_stats()
        stats["total_people"] = len(people)
        stats["helmet_count"] = sum(p["status"] == "HELMET" for p in people)
        stats["no_helmet_count"] = sum(p["status"] == "NO HELMET" for p in people)
        stats["unknown_count"] = sum(p["status"] == "UNKNOWN" for p in people)
        if stats["total_people"]:
            stats["helmet_percent"] = stats["helmet_count"] / stats["total_people"] * 100
            stats["no_helmet_percent"] = stats["no_helmet_count"] / stats["total_people"] * 100
        return stats
