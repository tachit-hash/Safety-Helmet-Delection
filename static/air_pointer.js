import { FilesetResolver, HandLandmarker } from "/vendor/mediapipe/vision_bundle.mjs";

const toggle = document.querySelector("#air-pointer-toggle");
const stopButton = document.querySelector("#air-pointer-stop");
const panel = document.querySelector("#air-pointer-panel");
const video = document.querySelector("#air-pointer-video");
const status = document.querySelector("#air-pointer-status");
const cursor = document.querySelector("#air-pointer-cursor");
const ring = cursor.querySelector(".air-pointer-ring");

let cameraStream = null;
let handLandmarker = null;
let animationFrame = 0;
let operationId = 0;
let lastDetectionAt = 0;
let currentTarget = null;
let dwellStartedAt = 0;
let needsLeaveReset = false;
let leaveStartedAt = 0;
let smoothedX = 0;
let smoothedY = 0;
let hasSmoothedPosition = false;

function setStatus(message, isError = false) {
  status.textContent = message;
  status.classList.toggle("air-pointer-error", isError);
}

function distanceFromWrist(landmark, wrist) {
  return Math.hypot(landmark.x - wrist.x, landmark.y - wrist.y);
}

function isPointing(landmarks) {
  const wrist = landmarks[0];
  const indexExtended = distanceFromWrist(landmarks[8], wrist)
    > distanceFromWrist(landmarks[6], wrist) * 1.12;
  const otherFingersCurled = [12, 16, 20].every((tip, index) => {
    const pip = [10, 14, 18][index];
    return distanceFromWrist(landmarks[tip], wrist)
      < distanceFromWrist(landmarks[pip], wrist) * 1.18;
  });
  return indexExtended && otherFingersCurled;
}

function findTarget(x, y) {
  const element = document.elementFromPoint(x, y);
  const target = element?.closest("button:not(:disabled), a[href]");
  if (!target || target.getAttribute("aria-disabled") === "true") return null;
  if (target.closest("#air-pointer-panel") || target.id === "air-pointer-toggle") return null;
  return target;
}

function clearDwell() {
  if (currentTarget) currentTarget.classList.remove("air-pointer-target");
  currentTarget = null;
  dwellStartedAt = 0;
  ring.style.setProperty("--dwell", "0%");
}

function updateDwell(x, y, now) {
  const target = findTarget(x, y);
  if (target !== currentTarget) {
    clearDwell();
    currentTarget = target;
    dwellStartedAt = now;
    if (currentTarget) currentTarget.classList.add("air-pointer-target");
  }

  if (needsLeaveReset) {
    if (target) {
      leaveStartedAt = 0;
      setStatus("Move away from the button to point again.");
    } else if (!leaveStartedAt) {
      leaveStartedAt = now;
    } else if (now - leaveStartedAt >= 450) {
      needsLeaveReset = false;
      leaveStartedAt = 0;
      setStatus("Point at a button for 1 second to select it.");
    }
    return;
  }

  if (!target) {
    setStatus("Point at a button for 1 second to select it.");
    return;
  }

  const progress = Math.min((now - dwellStartedAt) / 1000, 1);
  ring.style.setProperty("--dwell", `${progress * 100}%`);
  setStatus("Hold steady…");
  if (progress >= 1) {
    target.click();
    clearDwell();
    needsLeaveReset = true;
    leaveStartedAt = 0;
    setStatus("Selected. Move away from the button to point again.");
  }
}

function hidePointer() {
  clearDwell();
  cursor.classList.add("hidden");
  hasSmoothedPosition = false;
  leaveStartedAt = 0;
}

function trackFrame() {
  if (!handLandmarker || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
    animationFrame = window.requestAnimationFrame(trackFrame);
    return;
  }

  const now = performance.now();
  if (now - lastDetectionAt < 50) {
    animationFrame = window.requestAnimationFrame(trackFrame);
    return;
  }
  lastDetectionAt = now;

  try {
    const results = handLandmarker.detectForVideo(video, now);
    const landmarks = results.landmarks?.[0];
    if (!landmarks || !isPointing(landmarks)) {
      hidePointer();
      setStatus("Show one hand and point with your index finger.");
    } else {
      const targetX = (1 - landmarks[8].x) * window.innerWidth;
      const targetY = landmarks[8].y * window.innerHeight;
      if (!hasSmoothedPosition) {
        smoothedX = targetX;
        smoothedY = targetY;
        hasSmoothedPosition = true;
      } else {
        smoothedX += (targetX - smoothedX) * 0.48;
        smoothedY += (targetY - smoothedY) * 0.48;
      }
      cursor.style.left = `${smoothedX}px`;
      cursor.style.top = `${smoothedY}px`;
      cursor.classList.remove("hidden");
      updateDwell(smoothedX, smoothedY, now);
    }
  } catch (error) {
    stopPointing();
    panel.classList.remove("hidden");
    setStatus(`Hand tracking stopped: ${error.message}`, true);
    return;
  }

  animationFrame = window.requestAnimationFrame(trackFrame);
}

function stopPointing() {
  operationId += 1;
  window.cancelAnimationFrame(animationFrame);
  animationFrame = 0;
  lastDetectionAt = 0;
  if (handLandmarker) handLandmarker.close();
  handLandmarker = null;
  if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
  cameraStream = null;
  video.srcObject = null;
  panel.classList.add("hidden");
  hidePointer();
  needsLeaveReset = false;
  toggle.textContent = "Enable Point Control";
  toggle.setAttribute("aria-pressed", "false");
}

async function startPointing() {
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus("Camera access is unavailable. Open the dashboard on localhost or HTTPS.", true);
    panel.classList.remove("hidden");
    return;
  }

  toggle.disabled = true;
  const currentOperation = ++operationId;
  panel.classList.remove("hidden");
  setStatus("Allow camera access to enable pointing.");
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: "user",
        width: { ideal: 320 },
        height: { ideal: 240 },
        frameRate: { ideal: 20, max: 20 },
      },
    });
    if (currentOperation !== operationId) {
      cameraStream.getTracks().forEach((track) => track.stop());
      cameraStream = null;
      return;
    }
    video.srcObject = cameraStream;
    await video.play();
    setStatus("Loading hand tracking…");
    const vision = await FilesetResolver.forVisionTasks("/vendor/mediapipe/wasm");
    const options = {
      baseOptions: { modelAssetPath: "/static/models/hand_landmarker.task" },
      runningMode: "VIDEO",
      numHands: 1,
      minHandDetectionConfidence: 0.55,
      minHandPresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
    };
    try {
      handLandmarker = await HandLandmarker.createFromOptions(vision, {
        ...options,
        baseOptions: { ...options.baseOptions, delegate: "GPU" },
      });
    } catch {
      handLandmarker = await HandLandmarker.createFromOptions(vision, options);
    }
    if (currentOperation !== operationId) {
      handLandmarker.close();
      handLandmarker = null;
      if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
      cameraStream = null;
      video.srcObject = null;
      return;
    }
    toggle.textContent = "Point Control On";
    toggle.setAttribute("aria-pressed", "true");
    setStatus("Show one hand and point with your index finger.");
    animationFrame = window.requestAnimationFrame(trackFrame);
  } catch (error) {
    stopPointing();
    const message = error.name === "NotAllowedError"
      ? "Camera permission was denied. Allow camera access in your browser settings."
      : error.name === "NotFoundError"
        ? "No camera was found on this computer."
        : `Unable to start point control: ${error.message}`;
    panel.classList.remove("hidden");
    setStatus(message, true);
  } finally {
    toggle.disabled = false;
  }
}

toggle.addEventListener("click", () => {
  if (cameraStream) stopPointing();
  else startPointing();
});
stopButton.addEventListener("click", stopPointing);
