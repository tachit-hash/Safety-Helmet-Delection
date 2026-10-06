import cv2

class VisualRenderer:
    def __init__(self):
        self.COLOR_HELMET = (0, 255, 0)     
        self.COLOR_VIOLATION = (0, 0, 255)  
        self.COLOR_TEXT = (255, 255, 255)   
    def draw_detections(self, frame, detections):
        """
        :param frame: រូបភាពពី Camera/Video
        :param detections: List នៃ dict ឧ. [{'box': [x1, y1, x2, y2], 'label': 'Helmet', 'is_violation': False}]
        """
        for det in detections:
            x1, y1, x2, y2 = map(int, det['box'])
            is_violation = det.get('is_violation', False)
            label = det.get('label', 'Unknown')
            color = self.COLOR_VIOLATION if is_violation else self.COLOR_HELMET
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{label}"
            (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, y1 - text_h - 10), (x1 + text_w, y1), color, -1)
            cv2.putText(frame, text, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.COLOR_TEXT, 2)
        return frame
    def draw_dashboard(self, frame, stats_summary, fps=0):
        """
        គូរ Dashboard ស្ថិតិ Real-time នៅជ្រុងខាងលើ
        """
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (320, 120), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        cv2.putText(frame, f"FPS: {fps:.1f}", (20, 35), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Helmets: {stats_summary.get('Helmets', 0)}", (20, 65), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.COLOR_HELMET, 2)
        cv2.putText(frame, f"Violations: {stats_summary.get('Violations', 0)}", (20, 95), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.COLOR_VIOLATION, 2)
        return frame