class ObjectTracker:
    def __init__(self, iou_threshold=0.3, max_missed_frames=10):
        self.tracked_objects = {}
        self.iou_threshold = iou_threshold
        self.max_missed_frames = max_missed_frames
        self.next_track_id = 1

    def update(self, detections):
        detections = {key: list(value) for key, value in detections.items()}
        persons = detections.get("persons", [])
        unmatched_tracks = set(self.tracked_objects)
        updated_persons = []

        for person in persons:
            bbox = person["bbox"]
            best_track_id = None
            best_iou = self.iou_threshold

            for track_id in unmatched_tracks:
                iou = self._iou(bbox, self.tracked_objects[track_id]["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_track_id = track_id

            if best_track_id is None:
                best_track_id = self.next_track_id
                self.next_track_id += 1
                self.tracked_objects[best_track_id] = {
                    "bbox": bbox,
                    "missed_frames": 0,
                    "reported_statuses": set(),
                }
            else:
                unmatched_tracks.remove(best_track_id)
                track = self.tracked_objects[best_track_id]
                track["bbox"] = bbox
                track["missed_frames"] = 0

            updated_person = dict(person)
            updated_person["track_id"] = best_track_id
            updated_persons.append(updated_person)

        for track_id in list(self.tracked_objects):
            if track_id in unmatched_tracks:
                track = self.tracked_objects[track_id]
                track["missed_frames"] += 1
                if track["missed_frames"] > self.max_missed_frames:
                    del self.tracked_objects[track_id]

        detections["persons"] = updated_persons
        return detections

    def is_announced(self, track_id, status):
        track = self.tracked_objects.get(track_id)
        return track is None or status in track["reported_statuses"]

    def mark_announced(self, track_id, status):
        track = self.tracked_objects.get(track_id)
        if track is not None:
            track["reported_statuses"].add(status)

    @staticmethod
    def _iou(first_bbox, second_bbox):
        x1 = max(first_bbox[0], second_bbox[0])
        y1 = max(first_bbox[1], second_bbox[1])
        x2 = min(first_bbox[2], second_bbox[2])
        y2 = min(first_bbox[3], second_bbox[3])
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        if intersection == 0:
            return 0.0

        first_area = max(0, first_bbox[2] - first_bbox[0]) * max(0, first_bbox[3] - first_bbox[1])
        second_area = max(0, second_bbox[2] - second_bbox[0]) * max(0, second_bbox[3] - second_bbox[1])
        union = first_area + second_area - intersection
        return intersection / union if union else 0.0