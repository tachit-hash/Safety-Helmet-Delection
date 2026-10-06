class AssociationEngine:
    def __init__(self, head_ratio=0.4):
        self.head_ratio = head_ratio

    def is_inside_head_area(self, item_bbox, person_bbox):
        """
        Check if an item (helmet/head) overlaps with the upper portion of a person bounding box.
        """
        hx1, hy1, hx2, hy2 = item_bbox
        px1, py1, px2, py2 = person_bbox

        person_head_y2 = py1 + int((py2 - py1) * self.head_ratio)

        overlap_x = max(0, min(hx2, px2) - max(hx1, px1))
        overlap_y = max(0, min(hy2, person_head_y2) - max(hy1, py1))

        return overlap_x > 0 and overlap_y > 0

    def associate_and_classify(self, detections):
        """
        Associates helmet/no_helmet detections with persons and returns classified results.
        """
        results = []
        if not detections or "persons" not in detections:
            return results

        for person in detections.get("persons", []):
            p_bbox = person["bbox"]
            has_helmet = any(self.is_inside_head_area(h["bbox"], p_bbox) for h in detections.get("helmets", []))
            has_no_helmet = any(self.is_inside_head_area(nh["bbox"], p_bbox) for nh in detections.get("no_helmets", []))

            status = (
                "HELMET" if has_helmet
                else "NO HELMET" if has_no_helmet
                else "UNKNOWN"
            )

            result = {
                "bbox": p_bbox, 
                "conf": person["conf"], 
                "status": status
            }
            if "track_id" in person:
                result["track_id"] = person["track_id"]
            results.append(result)

        return results