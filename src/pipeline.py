from src.detector import HelmetDetector
from src.association import AssociationEngine
from src.tracker import ObjectTracker

class DetectionPipeline:
    def __init__(self):
        self.detector = HelmetDetector()
        self.associator = AssociationEngine()
        self.tracker = ObjectTracker()
    def process_frame(self, frame):
        detections = self.detector.detect(frame)
        tracked_detections = self.tracker.update(detections)
        results = self.associator.associate_and_classify(tracked_detections)
        if not self.detector.helmet_detection_available:
            for index, person in enumerate(results):
                other_person_bboxes = [
                    other["bbox"]
                    for other_index, other in enumerate(results)
                    if other_index != index
                ]
                person["status"] = (
                    "HELMET"
                    if self.detector.has_colored_headgear(
                        frame,
                        person["bbox"],
                        other_person_bboxes,
                    )
                    else "NO HELMET"
                )
        return results