import csv
import os
import tempfile

from flask import Flask, Response, jsonify, render_template, send_file, send_from_directory

from src.logger import ViolationLogger
from src.web_service import ScanService


app = Flask(__name__)
scan_service = ScanService()
event_logger = ViolationLogger()
VISION_PACKAGE_DIR = os.path.join(
    os.path.dirname(__file__),
    "node_modules",
    "@mediapipe",
    "tasks-vision",
)


@app.get("/vendor/mediapipe/<path:filename>")
def mediapipe_asset(filename):
    allowed_assets = {
        "vision_bundle.mjs",
        "wasm/vision_wasm_internal.js",
        "wasm/vision_wasm_internal.wasm",
        "wasm/vision_wasm_module_internal.js",
        "wasm/vision_wasm_module_internal.wasm",
        "wasm/vision_wasm_nosimd_internal.js",
        "wasm/vision_wasm_nosimd_internal.wasm",
    }
    if filename not in allowed_assets:
        return jsonify({"error": "MediaPipe asset not found."}), 404
    return send_from_directory(VISION_PACKAGE_DIR, filename)


@app.get("/")
def dashboard():
    return render_template("dashboard.html")


@app.get("/api/status")
def scan_status():
    return jsonify(scan_service.status())


@app.post("/api/scan/start")
def start_scan():
    started = scan_service.start()
    return jsonify(scan_service.status()), 202 if started else 200


@app.post("/api/scan/stop")
def stop_scan():
    scan_service.stop()
    return jsonify(scan_service.status())


@app.get("/api/history")
def scan_history():
    records = []
    if os.path.exists(event_logger.csv_file):
        with open(event_logger.csv_file, newline="", encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                image_path = row.get("Image_Path", "")
                row["Image_Name"] = os.path.basename(image_path) if image_path else ""
                records.append(row)
    records.reverse()
    return jsonify(records)


@app.get("/api/history/<image_name>")
def scan_history_detail(image_name):
    if not image_name or os.path.basename(image_name) != image_name:
        return jsonify({"error": "Invalid image name."}), 400

    if not os.path.exists(event_logger.csv_file):
        return jsonify({"error": "Scan record not found."}), 404

    with open(event_logger.csv_file, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if os.path.basename(row.get("Image_Path", "")) == image_name:
                row["Image_Name"] = image_name
                return jsonify(row)

    return jsonify({"error": "Scan record not found."}), 404


@app.post("/api/history/<image_name>/delete")
def delete_scan(image_name):
    if not image_name or os.path.basename(image_name) != image_name:
        return jsonify({"error": "Invalid image name."}), 400

    image_path = os.path.realpath(os.path.join(event_logger.output_dir, image_name))
    storage_path = os.path.realpath(event_logger.output_dir)
    if os.path.commonpath([storage_path, image_path]) != storage_path:
        return jsonify({"error": "Deleting this file is not allowed."}), 400

    try:
        with open(event_logger.csv_file, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            if not fieldnames:
                return jsonify({"error": "No scan history is available."}), 404
            rows = list(reader)

        matching_rows = [
            row for row in rows
            if os.path.basename(row.get("Image_Path", "")) == image_name
        ]
        if not matching_rows:
            return jsonify({"error": "Scan record not found."}), 404

        remaining_rows = [
            row for row in rows
            if os.path.basename(row.get("Image_Path", "")) != image_name
        ]

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                newline="",
                encoding="utf-8-sig",
                dir=storage_path,
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                writer = csv.DictWriter(temporary_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(remaining_rows)

            if os.path.exists(image_path):
                os.remove(image_path)
            os.replace(temporary_path, event_logger.csv_file)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.remove(temporary_path)

        return jsonify({"deleted": True, "image_name": image_name})
    except OSError as error:
        app.logger.exception("Failed to delete scan record %s", image_name)
        return jsonify({"error": f"Unable to delete the record: {error}"}), 500


@app.get("/api/export")
def export_history():
    return send_file(
        event_logger.csv_file,
        mimetype="text/csv",
        as_attachment=True,
        download_name="helmet_detection_history.csv",
    )


@app.get("/scans/<path:filename>")
def scan_image(filename):
    return send_from_directory(event_logger.output_dir, filename)


@app.get("/api/live")
def live_stream():
    def frames():
        while scan_service.status()["running"]:
            image = scan_service.latest_jpeg()
            if image:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + image + b"\r\n"
            scan_service.wait_for_frame(0.05)

    return Response(
        frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"},
    )


if __name__ == "__main__":
    print("Open the safety helmet dashboard at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, threaded=True, use_reloader=False)
