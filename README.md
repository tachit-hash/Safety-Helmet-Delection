# Safety Helmet Detection System

An AI-powered real-time safety helmet detection system built using YOLOv8 and OpenCV.

## Features
- Real-time person and safety helmet detection via Webcam.
- Spatial association to detect non-compliant individuals.
- Live dashboard showing person counts and helmet-status percentages.
- Timestamped image and CSV records in the `violations/` folder for later review.
- Browser dashboard with Dashboard, Live Camera, Cameras, Videos (saved scan images), Detections, Reports, Users, and Settings sections.
- Dashboard interface, scan messages, and reports are displayed in English.
- Per-scan detail pages, saved-image preview, scan-record summaries, and CSV export.
- Dashboard overview with saved detection totals, a seven-day helmet-status chart, active default-camera state, and recent detections.
- Reports page with selectable date range, detection totals, daily trend, helmet compliance ratio, and a filtered CSV download.
- Optional touch-free point control: point at a dashboard button for one second to activate it.
- Hand tracking runs locally in the browser. The camera feed is not uploaded.
- Helmet detection runs every 10 seconds while the camera preview remains live.
- Dashboard status examples use the user-provided helmet and no-helmet images.
- A popup appears when a person is newly detected during a scan.

Helmet classification requires a YOLO model trained with helmet and no-helmet
classes. The included `yolov8n.pt` model detects general COCO objects and does
not provide helmet-status classes. Without helmet-trained weights, the app
checks the upper part of each detected person's bounding box for blue, yellow,
red, pink, purple, or white regions: a matching region is marked with a green
check; no matching region is marked with a red cross. This color heuristic can
mistake similarly colored backgrounds or clothing for headwear. Configure
`MODEL_PATH` in `src/config.py` with helmet-trained model weights for reliable
helmet classification. A short browser sound alert plays for new no-helmet
detections after the user starts scanning.

To train a compatible model, collect varied images of people both wearing
safety helmets and without them, then annotate every person and each visible
head as `person`, `helmet`, or `no_helmet`. Use YOLO detection format with
class IDs `0: person`, `1: helmet`, `2: no_helmet`; split images and matching
label text files into `train` and `val` folders. One helmet sample image alone
is not enough to train a reliable detector. After training, point `MODEL_PATH`
at the resulting `best.pt` file.

Each CSV record includes the event time, saved image path, detection status,
counts, and helmet/no-helmet percentages. Open `violations/violations_log.csv`
to review events; the linked images are stored alongside the CSV file.

## Project Structure
```text
safety-helmet-detection/
├── models/
│   └── yolov8n.pt
├── src/
│   ├── association.py
│   ├── config.py
│   ├── detector.py
│   ├── logger.py
│   ├── pipeline.py
│   └── tracker.py
├── violations/
├── app.py
└── README.md
```

## How to Run
1. Install Python, Node.js, and npm, then install the project dependencies:
   ```bash
   pip install ultralytics opencv-python flask
   npm install
   ```
2. Set `MODEL_PATH` in `src/config.py` to a helmet-trained YOLO weights file.
3. Start the application:
   ```bash
   python app.py
   ```
4. Open `http://127.0.0.1:5000` in your browser and select **Start Scan**.

Select **Enable Point Control** in the dashboard to use hands-free navigation.
Allow camera access, show one hand, and point with your index finger while
curling the other fingers. The on-screen pointer highlights its target; hold
over a button for one second to activate it. Move off the target before
selecting another control. Select **Turn off** to stop the camera and release
the browser's camera access.

Use the **Scan History** page to view saved detection images and event
percentages. Open a record's **Details** view to see its saved image, status,
person-detection confidence (for new records), timestamp, and frame counts.
Only still images are saved; no video clips or frame sequences are recorded.
The **Download CSV** button exports the saved records. Keep the application
running while using the dashboard.
The Cameras page currently reports the default webcam (index 0); multiple
cameras are not configurable. Users and Settings pages report the local
single-user setup and current fixed scan/storage settings; account management
and editing settings in the dashboard are not currently supported.