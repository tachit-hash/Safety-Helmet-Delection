const titles = {
  dashboard: "Dashboard",
  live: "Live Camera",
  cameras: "Cameras",
  videos: "Videos",
  history: "Detections",
  reports: "Reports",
  users: "Users",
  settings: "Settings",
  detail: "Detection Details",
};
const subtitles = {
  dashboard: "Safety helmet detection system overview",
  live: "View the live camera and scan status",
  cameras: "Information about the system camera source",
  videos: "Browse saved scan images",
  history: "Review and manage saved detections",
  reports: "View and download system reports",
  users: "System user information",
  settings: "View current system settings",
  detail: "Detection details and image",
};

const $ = (selector) => document.querySelector(selector);
let allHistoryRecords = [];

function closeTopbarMenus() {
  $("#notification-menu").classList.add("hidden");
  $("#profile-menu").classList.add("hidden");
  $("#notification-toggle").setAttribute("aria-expanded", "false");
  $("#profile-toggle").setAttribute("aria-expanded", "false");
}

function showView(name, updateHash = true) {
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  const activeView = name === "detail" ? "history" : name;
  document.querySelectorAll(".nav-link").forEach((link) => link.classList.toggle("active", link.dataset.view === activeView));
  $("#page-title").textContent = titles[name];
  $("#page-subtitle").textContent = subtitles[name];
  closeTopbarMenus();
  if (["dashboard", "history", "videos", "reports"].includes(name)) loadHistory();
  if (updateHash) window.location.hash = name;
}

document.querySelectorAll(".nav-link").forEach((link) => link.addEventListener("click", () => showView(link.dataset.view)));
document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.go)));

function renderNotifications(records) {
  const container = $("#notification-list");
  container.replaceChildren();
  $("#notification-dot").classList.toggle("hidden", records.length === 0);
  if (!records.length) {
    const empty = document.createElement("p");
    empty.className = "popover-empty";
    empty.textContent = "No detections yet";
    container.append(empty);
    return;
  }
  records.slice(0, 5).forEach((record) => {
    const item = document.createElement("button");
    item.className = "notification-item";
    item.type = "button";
    item.append(makeStatus(record.Status));
    const details = document.createElement("span");
    details.className = "notification-item-details";
    const message = document.createElement("strong");
    message.textContent = statusLabel(record.Status);
    const time = document.createElement("small");
    time.textContent = formatTimestamp(record.Timestamp);
    details.append(message, time);
    item.append(details);
    item.addEventListener("click", () => {
      closeTopbarMenus();
      if (record.Image_Name) openDetectionDetail(record.Image_Name);
      else showView("history");
    });
    container.append(item);
  });
}

function toggleTopbarMenu(menuName) {
  const menu = $(`#${menuName}-menu`);
  const button = $(`#${menuName}-toggle`);
  const shouldOpen = menu.classList.contains("hidden");
  closeTopbarMenus();
  if (shouldOpen) {
    menu.classList.remove("hidden");
    button.setAttribute("aria-expanded", "true");
  }
}

$("#notification-toggle").addEventListener("click", () => toggleTopbarMenu("notification"));
$("#profile-toggle").addEventListener("click", () => toggleTopbarMenu("profile"));
document.addEventListener("click", (event) => {
  if (!event.target.closest(".topbar-menu-wrap")) closeTopbarMenus();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeTopbarMenus();
});

function localDateInputValue(date) {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return localDate.toISOString().slice(0, 10);
}

function initializeReportDates() {
  const today = new Date();
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 6);
  $("#report-start-date").value = localDateInputValue(weekAgo);
  $("#report-end-date").value = localDateInputValue(today);
}

initializeReportDates();

function formatTimestamp(value) {
  if (!value) return "—";
  const parsed = new Date(value.replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("en-US", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(parsed);
}

function statusClass(status) {
  if (status === "HELMET") return "helmet";
  if (status === "NO HELMET") return "no-helmet";
  return "unknown";
}

function statusLabel(status) {
  if (status === "HELMET") return "Helmet";
  if (status === "NO HELMET") return "No Helmet";
  return "Unknown";
}

function makeStatus(status) {
  const badge = document.createElement("span");
  badge.className = `status-pill ${statusClass(status)}`;
  badge.textContent = statusLabel(status);
  return badge;
}

async function loadHistory() {
  const body = $("#history-body");
  try {
    const response = await fetch("/api/history");
    if (!response.ok) throw new Error("Unable to load detection history.");
    const records = await response.json();
    allHistoryRecords = records;
      $("#history-count").textContent = `${records.length} records`;
    $("#detection-count").textContent = records.length > 99 ? "99+" : records.length;
    renderNotifications(records);
    renderDashboardOverview(records);
    renderVideoGallery(records);
    renderReports(records);
    body.replaceChildren();
    if (!records.length) {
      const row = body.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 9;
      cell.className = "empty-cell";
      cell.textContent = "No saved scans yet.";
      renderRecent([]);
      return;
    }
    for (const record of records) {
      const row = body.insertRow();
      const imageCell = row.insertCell();
      if (record.Image_Name) {
        const image = document.createElement("img");
        image.className = "history-image";
        image.src = `/scans/${encodeURIComponent(record.Image_Name)}`;
        image.alt = "Scan image";
        image.loading = "lazy";
        image.addEventListener("click", () => openImage(image.src));
        imageCell.append(image);
      } else {
        const placeholder = document.createElement("span");
        placeholder.className = "no-image";
        placeholder.textContent = "No image";
        imageCell.append(placeholder);
      }
      row.insertCell().textContent = formatTimestamp(record.Timestamp);
      row.insertCell().append(makeStatus(record.Status));
      row.insertCell().textContent = record.Total_People || "0";
      row.insertCell().textContent = record.Helmet_Count || "0";
      row.insertCell().textContent = record.No_Helmet_Count || "0";
      row.insertCell().textContent = `${record.Helmet_Percent || "0"}%`;
      row.insertCell().textContent = `${record.No_Helmet_Percent || "0"}%`;
      const actionCell = row.insertCell();
      if (record.Image_Name) {
        const detailButton = document.createElement("button");
        detailButton.className = "button detail-button";
        detailButton.type = "button";
        detailButton.textContent = "Details";
        detailButton.addEventListener("click", () => openDetectionDetail(record.Image_Name));
        actionCell.append(detailButton);

        const deleteButton = document.createElement("button");
        deleteButton.className = "button delete-button";
        deleteButton.type = "button";
        deleteButton.textContent = "Delete";
        deleteButton.setAttribute("aria-label", `Delete record ${formatTimestamp(record.Timestamp)}`);
        deleteButton.addEventListener("click", () => deleteRecord(record));
        deleteButton.classList.add("history-delete-button");
        actionCell.append(deleteButton);
      } else {
        actionCell.textContent = "—";
      }
    }
    renderRecent(records.slice(0, 5));
  } catch (error) {
    $("#video-gallery").textContent = error.message;
    body.replaceChildren();
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 9;
    cell.className = "empty-cell";
    cell.textContent = error.message;
  }
}

function renderVideoGallery(records) {
  const gallery = $("#video-gallery");
  gallery.replaceChildren();
  const imageRecords = records.filter((record) => record.Image_Name);
  if (!imageRecords.length) {
    const empty = document.createElement("p");
    empty.className = "empty-cell";
    empty.textContent = "No saved scan images yet.";
    gallery.append(empty);
    return;
  }
  for (const record of imageRecords) {
    const card = document.createElement("article");
    card.className = "video-card";
    const image = document.createElement("img");
    image.src = `/scans/${encodeURIComponent(record.Image_Name)}`;
    image.alt = "Saved scan image";
    image.loading = "lazy";
    image.addEventListener("click", () => openDetectionDetail(record.Image_Name));
    const caption = document.createElement("div");
    caption.className = "video-card-caption";
    const time = document.createElement("span");
    time.textContent = formatTimestamp(record.Timestamp);
    caption.append(time, makeStatus(record.Status));
    const detailButton = document.createElement("button");
    detailButton.className = "button detail-button";
    detailButton.type = "button";
    detailButton.textContent = "Details";
    detailButton.addEventListener("click", () => openDetectionDetail(record.Image_Name));
    card.append(image, caption, detailButton);
    gallery.append(card);
  }
}

function getReportRecords(records) {
  const startDate = $("#report-start-date").value;
  const endDate = $("#report-end-date").value;
  if (startDate && endDate && startDate > endDate) {
    throw new Error("The start date must be before or equal to the end date.");
  }
  return records.filter((record) => {
    const recordDate = record.Timestamp ? record.Timestamp.slice(0, 10) : "";
    return recordDate && (!startDate || recordDate >= startDate) && (!endDate || recordDate <= endDate);
  });
}

function renderReports(records) {
  try {
    const selected = getReportRecords(records);
    const totals = selected.reduce((result, record) => {
      const counts = recordCounts(record);
      result.total += counts.total;
      result.helmet += counts.helmet;
      result.noHelmet += counts.noHelmet;
      result.unknown += counts.unknown;
      return result;
    }, { total: 0, helmet: 0, noHelmet: 0, unknown: 0 });
    const classified = totals.helmet + totals.noHelmet;
    const helmetPercent = classified ? totals.helmet / classified * 100 : 0;
    const noHelmetPercent = classified ? totals.noHelmet / classified * 100 : 0;
    $("#report-total").textContent = totals.total;
    $("#report-helmet").textContent = totals.helmet;
    $("#report-no-helmet").textContent = totals.noHelmet;
    $("#report-violations").textContent = totals.noHelmet;
    $("#report-helmet-ratio").textContent = `${helmetPercent.toFixed(1)}%`;
    $("#report-no-helmet-ratio").textContent = `${noHelmetPercent.toFixed(1)}%`;
    $("#report-compliance-ratio").textContent = `${helmetPercent.toFixed(1)}%`;
    $("#report-ratio-helmet-count").textContent = totals.helmet;
    $("#report-ratio-no-helmet-count").textContent = totals.noHelmet;
    $("#report-ratio-chart").style.setProperty("--helmet-ratio", `${helmetPercent}%`);
    $("#report-ratio-chart").setAttribute(
      "aria-label",
      `Helmet ${helmetPercent.toFixed(1)} percent and no helmet ${noHelmetPercent.toFixed(1)} percent`,
    );
    renderTrendChart("#report-trend-chart", selected, $("#report-start-date").value, $("#report-end-date").value);
    $("#error-banner").classList.add("hidden");
  } catch (error) {
    $("#report-total").textContent = "—";
    $("#report-helmet").textContent = "—";
    $("#report-no-helmet").textContent = "—";
    $("#report-violations").textContent = "—";
    $("#report-helmet-ratio").textContent = "—";
    $("#report-no-helmet-ratio").textContent = "—";
    $("#report-compliance-ratio").textContent = "—";
    $("#report-ratio-helmet-count").textContent = "—";
    $("#report-ratio-no-helmet-count").textContent = "—";
    $("#report-ratio-chart").style.setProperty("--helmet-ratio", "0%");
    $("#report-trend-chart").replaceChildren();
    $("#error-banner").textContent = error.message;
    $("#error-banner").classList.remove("hidden");
  }
}

function recordCounts(record) {
  const count = (value, fallback) => {
    const parsed = Number(value);
    return value !== "" && value != null && Number.isFinite(parsed) ? parsed : fallback;
  };
  const statusHelmet = record.Status === "HELMET" ? 1 : 0;
  const statusNoHelmet = record.Status === "NO HELMET" ? 1 : 0;
  const statusUnknown = statusHelmet || statusNoHelmet ? 0 : 1;
  const helmet = count(record.Helmet_Count, statusHelmet);
  const noHelmet = count(record.No_Helmet_Count, statusNoHelmet);
  const unknown = count(record.Unknown_Count, statusUnknown);
  return {
    helmet,
    noHelmet,
    unknown,
    total: count(record.Total_People, helmet + noHelmet + unknown),
  };
}

function renderDashboardOverview(records) {
  const totals = records.reduce((result, record) => {
    const counts = recordCounts(record);
    result.total += counts.total;
    result.helmet += counts.helmet;
    result.noHelmet += counts.noHelmet;
    return result;
  }, { total: 0, helmet: 0, noHelmet: 0 });
  $("#overview-total").textContent = totals.total;
  $("#overview-helmet").textContent = totals.helmet;
  $("#overview-no-helmet").textContent = totals.noHelmet;
  const parsedDates = records
    .map((record) => record.Timestamp ? new Date(record.Timestamp.replace(" ", "T")) : null)
    .filter((date) => date && !Number.isNaN(date.getTime()));
  const endDate = parsedDates.reduce(
    (latest, date) => !latest || date > latest ? date : latest,
    null,
  ) || new Date();
  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 6);
  renderTrendChart("#overview-chart", records, localDateInputValue(startDate), localDateInputValue(endDate));
}

function appendSvgElement(svg, name, attributes = {}, text = "") {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  if (text) element.textContent = text;
  svg.append(element);
  return element;
}

function renderTrendChart(selector, records, startDate, endDate) {
  const svg = $(selector);
  svg.replaceChildren();
  const start = startDate ? new Date(`${startDate}T00:00:00`) : new Date();
  const end = endDate ? new Date(`${endDate}T00:00:00`) : new Date();
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) return;
  const totalDays = Math.floor((end - start) / 86400000) + 1;
  const slotCount = Math.min(totalDays, 14);
  const slots = Array.from({ length: slotCount }, (_, index) => {
    const dayOffset = Math.floor(index * totalDays / slotCount);
    const date = new Date(start);
    date.setDate(date.getDate() + dayOffset);
    return { date, helmet: 0, noHelmet: 0 };
  });
  for (const record of records) {
    const recordDate = record.Timestamp ? new Date(`${record.Timestamp.slice(0, 10)}T00:00:00`) : null;
    if (!recordDate || Number.isNaN(recordDate.getTime()) || recordDate < start || recordDate > end) continue;
    const dayOffset = Math.floor((recordDate - start) / 86400000);
    const slotIndex = Math.min(slotCount - 1, Math.floor(dayOffset * slotCount / totalDays));
    const counts = recordCounts(record);
    slots[slotIndex].helmet += counts.helmet;
    slots[slotIndex].noHelmet += counts.noHelmet;
  }

  const chartLeft = 48;
  const chartRight = 548;
  const chartTop = 20;
  const chartBottom = 176;
  const values = slots.flatMap((slot) => [slot.helmet, slot.noHelmet]);
  const maxValue = Math.max(4, ...values);
  const yMax = Math.ceil(maxValue / 4) * 4;
  const xForIndex = (index) => chartLeft + index * (chartRight - chartLeft) / Math.max(1, slots.length - 1);
  const yForValue = (value) => chartBottom - value * (chartBottom - chartTop) / yMax;

  for (let step = 0; step <= 4; step += 1) {
    const value = yMax * step / 4;
    const y = yForValue(value);
    appendSvgElement(svg, "line", { x1: chartLeft, y1: y, x2: chartRight, y2: y, class: "chart-gridline" });
    appendSvgElement(svg, "text", { x: chartLeft - 10, y: y + 4, class: "chart-axis-label", "text-anchor": "end" }, String(Math.round(value)));
  }

  const series = [
    { key: "helmet", className: "chart-line chart-line-helmet", pointClass: "chart-point-helmet", label: "Helmet detections" },
    { key: "noHelmet", className: "chart-line chart-line-no-helmet", pointClass: "chart-point-no-helmet", label: "No-helmet detections" },
  ];
  for (const item of series) {
    const points = slots.map((slot, index) => `${xForIndex(index)},${yForValue(slot[item.key])}`);
    appendSvgElement(svg, "polyline", {
      points: points.join(" "),
      class: item.className,
      "aria-label": item.label,
    });
    slots.forEach((slot, index) => {
      appendSvgElement(svg, "circle", {
        cx: xForIndex(index),
        cy: yForValue(slot[item.key]),
        r: 3,
        class: item.pointClass,
      });
    });
  }
  const tickStep = Math.max(1, Math.ceil(slots.length / 7));
  slots.forEach((slot, index) => {
    if (index % tickStep !== 0 && index !== slots.length - 1) return;
    const label = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(slot.date);
    appendSvgElement(svg, "text", {
      x: xForIndex(index),
      y: chartBottom + 22,
      class: "chart-axis-label chart-date-label",
      "text-anchor": "middle",
    }, label);
  });
}

async function deleteRecord(record) {
  const description = `${formatTimestamp(record.Timestamp)} · ${statusLabel(record.Status)}`;
  if (!window.confirm(`Delete this record and its image?\n${description}`)) return;

  try {
    const response = await fetch(`/api/history/${encodeURIComponent(record.Image_Name)}/delete`, {
      method: "POST",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Unable to delete the record.");
    $("#error-banner").classList.add("hidden");
    await loadHistory();
  } catch (error) {
    $("#error-banner").textContent = error.message;
    $("#error-banner").classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function renderRecent(records) {
  const body = $("#recent-body");
  body.replaceChildren();
  if (!records.length) {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 5;
    cell.className = "empty-cell";
    cell.textContent = "No records yet.";
    return;
  }
  records.forEach((record) => {
    const row = body.insertRow();
    row.insertCell().textContent = "Camera 0";
    row.insertCell().append(makeStatus(record.Status));
    row.insertCell().textContent = formatTimestamp(record.Timestamp);
    const confidence = Number(record.Confidence);
    row.insertCell().textContent = record.Confidence !== "" && Number.isFinite(confidence)
      ? `${(confidence * 100).toFixed(1)}%`
      : "—";
    const actionCell = row.insertCell();
    const detailButton = document.createElement("button");
    detailButton.className = "button detail-button";
    detailButton.type = "button";
    detailButton.textContent = "View";
    detailButton.disabled = !record.Image_Name;
    detailButton.addEventListener("click", () => openDetectionDetail(record.Image_Name));
    actionCell.append(detailButton);
  });
}

async function openDetectionDetail(imageName, updateHash = true) {
  if (!imageName) return;
  try {
    const response = await fetch(`/api/history/${encodeURIComponent(imageName)}`);
    const record = await response.json();
    if (!response.ok) throw new Error(record.error || "Unable to open detection details.");

    const imageUrl = `/scans/${encodeURIComponent(record.Image_Name)}`;
    $("#detail-event-id").textContent = `Record · ${record.Image_Name.replace(/\.jpg$/i, "")}`;
    $("#detail-image").src = imageUrl;
    $("#detail-image-link").href = imageUrl;
    $("#detail-image-status").replaceChildren(makeStatus(record.Status));
    $("#detail-status").replaceChildren(makeStatus(record.Status));
    $("#detail-confidence").textContent = record.Confidence
      ? `${(Number(record.Confidence) * 100).toFixed(1)}%`
      : "No data";
    $("#detail-time").textContent = formatTimestamp(record.Timestamp);
    $("#detail-path").textContent = record.Image_Name;
    $("#detail-download").href = imageUrl;
    $("#detail-helmet-count").textContent = record.Helmet_Count || "0";
    $("#detail-no-helmet-count").textContent = record.No_Helmet_Count || "0";
    $("#detail-unknown-count").textContent = record.Unknown_Count || "0";
    showView("detail", false);
    if (updateHash) window.location.hash = `detail/${encodeURIComponent(record.Image_Name)}`;
    $("#error-banner").classList.add("hidden");
  } catch (error) {
    $("#error-banner").textContent = error.message;
    $("#error-banner").classList.remove("hidden");
  }
}

function openImage(source) {
  $("#modal-image").src = source;
  $("#image-modal").classList.remove("hidden");
}
$("#modal-close").addEventListener("click", () => $("#image-modal").classList.add("hidden"));
$("#image-modal").addEventListener("click", (event) => {
  if (event.target.id === "image-modal") event.currentTarget.classList.add("hidden");
});
$("#refresh-history").addEventListener("click", loadHistory);
$("#detail-back").addEventListener("click", () => showView("history"));
$("#report-start-date").addEventListener("change", () => renderReports(allHistoryRecords));
$("#report-end-date").addEventListener("change", () => renderReports(allHistoryRecords));

function downloadReport() {
  let records;
  try {
    records = getReportRecords(allHistoryRecords);
  } catch (error) {
    renderReports(allHistoryRecords);
    $("#error-banner").textContent = error.message;
    $("#error-banner").classList.remove("hidden");
    return;
  }
  renderReports(allHistoryRecords);
  const columns = [
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
  ];
  const escapeCsv = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [
    columns.map(escapeCsv).join(","),
    ...records.map((record) => columns.map((column) => escapeCsv(record[column])).join(",")),
  ].join("\r\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `helmet_report_${$("#report-start-date").value}_to_${$("#report-end-date").value}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

$("#generate-report").addEventListener("click", downloadReport);
let popupTimeout;
let lastDetectionEventId = 0;
let alertAudioContext = null;

function enableAlertAudio() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    $("#warning-banner").textContent = "Sound alerts are not supported by this browser.";
    $("#warning-banner").classList.remove("hidden");
    return;
  }
  try {
    alertAudioContext ||= new AudioContextClass();
    if (alertAudioContext.state === "suspended") {
      alertAudioContext.resume().catch(() => {
        $("#warning-banner").textContent = "Allow sound in your browser to hear no-helmet alerts.";
        $("#warning-banner").classList.remove("hidden");
      });
    }
  } catch (error) {
    $("#warning-banner").textContent = `Unable to enable sound alerts: ${error.message}`;
    $("#warning-banner").classList.remove("hidden");
  }
}

function playNoHelmetAlert() {
  if (!alertAudioContext || alertAudioContext.state !== "running") return;
  const startAt = alertAudioContext.currentTime;
  const oscillator = alertAudioContext.createOscillator();
  const volume = alertAudioContext.createGain();
  oscillator.type = "sine";
  oscillator.frequency.setValueAtTime(880, startAt);
  volume.gain.setValueAtTime(0.0001, startAt);
  volume.gain.exponentialRampToValueAtTime(0.16, startAt + 0.02);
  volume.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.28);
  oscillator.connect(volume);
  volume.connect(alertAudioContext.destination);
  oscillator.start(startAt);
  oscillator.stop(startAt + 0.3);
}

function showDetectionPopup(event) {
  if (!event || event.id <= lastDetectionEventId) return;
  lastDetectionEventId = event.id;
  if ((event.statuses || []).includes("NO HELMET")) playNoHelmetAlert();

  const popup = $("#scan-popup");
  const image = $("#scan-popup-image");
  const unknown = $("#scan-popup-unknown");
  const detectedStatuses = [...new Set(event.statuses || [])];
  const status = detectedStatuses.length === 1 ? detectedStatuses[0] : "MULTIPLE";
  const isHelmet = status === "HELMET";
  const isNoHelmet = status === "NO HELMET";
  popup.classList.remove("hidden", "helmet", "no-helmet", "unknown");
  popup.classList.add(isHelmet ? "helmet" : isNoHelmet ? "no-helmet" : "unknown");

  if (isHelmet || isNoHelmet) {
    image.src = isHelmet
      ? "/static/images/helmet-example.png"
      : "/static/images/no-helmet-example.png";
    image.alt = isHelmet ? "Helmet example" : "No-helmet example";
    image.classList.remove("hidden");
    unknown.classList.add("hidden");
  } else {
    image.classList.add("hidden");
    unknown.classList.remove("hidden");
  }

  const titlesByStatus = {
    HELMET: "Helmet detected",
    "NO HELMET": "No helmet detected",
    UNKNOWN: "Person detected — status unknown",
    MULTIPLE: "New people detected",
  };
  $("#scan-popup-title").textContent = titlesByStatus[status] || titlesByStatus.UNKNOWN;
  $("#scan-popup-counts").textContent =
    `Helmet: ${event.helmet_count} · No helmet: ${event.no_helmet_count} · Unknown: ${event.unknown_count}`;

  window.clearTimeout(popupTimeout);
  popupTimeout = window.setTimeout(() => popup.classList.add("hidden"), 7000);
}

$("#scan-popup-close").addEventListener("click", () => {
  window.clearTimeout(popupTimeout);
  $("#scan-popup").classList.add("hidden");
});

async function sendAction(action) {
  if (action === "start") enableAlertAudio();
  try {
    const response = await fetch(`/api/scan/${action}`, { method: "POST" });
    if (!response.ok) throw new Error(`Unable to ${action === "start" ? "start" : "stop"} scanning.`);
    await refreshStatus();
  } catch (error) {
    $("#error-banner").textContent = error.message;
    $("#error-banner").classList.remove("hidden");
  }
}
$("#main-start").addEventListener("click", () => sendAction("start"));
$("#main-stop").addEventListener("click", () => sendAction("stop"));
$("#live-start").addEventListener("click", () => sendAction("start"));
$("#live-stop").addEventListener("click", () => sendAction("stop"));

function setLiveImage(running) {
  for (const id of ["dashboard-video", "live-video"]) {
    const image = $(`#${id}`);
    const placeholder = $(`#${id === "dashboard-video" ? "dashboard-placeholder" : "live-placeholder"}`);
    image.classList.toggle("hidden", !running);
    placeholder.classList.toggle("hidden", running);
    if (running && !image.src.includes("/api/live")) image.src = `/api/live?start=${Date.now()}`;
    if (!running) image.removeAttribute("src");
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("Unable to check system status.");
    const state = await response.json();
    showDetectionPopup(state.last_detection_event);
    $("#error-banner").classList.toggle("hidden", !state.error);
    $("#error-banner").textContent = state.error || "";
    $("#warning-banner").classList.toggle("hidden", !state.warning);
    $("#warning-banner").textContent = state.warning || "";

    $("#sidebar-status").textContent = state.running ? "Scanning" : "Not Started";
    $("#sidebar-dot").classList.toggle("running", state.running);
    $("#camera-page-badge").classList.toggle("running", state.running);
    $("#camera-page-badge").lastChild.textContent = state.running ? " Online" : " Offline";
    $("#overview-cameras").textContent = state.running ? "1 / 1" : "0 / 1";
    const scanInterval = Number(state.scan_interval_seconds);
    if (Number.isFinite(scanInterval) && scanInterval > 0) {
      $("#settings-interval").textContent = `${new Intl.NumberFormat("en-US").format(scanInterval)} seconds`;
    }
    $("#live-badge").classList.toggle("running", state.running);
    $("#live-badge-large").classList.toggle("running", state.running);
    $("#live-badge").lastChild.textContent = state.running ? " Scanning" : " Offline";
    $("#live-badge-large").lastChild.textContent = state.running ? " Scanning" : " Offline";
    $("#live-caption").textContent = state.running
      ? `Receiving video · Next scan in ${state.next_scan_in ?? 0} seconds`
      : "Ready to start";
    $("#main-start").classList.toggle("hidden", state.running);
    $("#main-stop").classList.toggle("hidden", !state.running);
    $("#live-start").classList.toggle("hidden", state.running);
    $("#live-stop").classList.toggle("hidden", !state.running);
    setLiveImage(state.running);

    $("#metric-total").textContent = state.total_people || 0;
    $("#metric-helmet").textContent = state.helmet_count || 0;
    $("#metric-no-helmet").textContent = state.no_helmet_count || 0;
    $("#metric-unknown").textContent = state.unknown_count || 0;
    $("#metric-helmet-percent").textContent = `${Number(state.helmet_percent || 0).toFixed(1)}% of detected people`;
    $("#metric-no-helmet-percent").textContent = `${Number(state.no_helmet_percent || 0).toFixed(1)}% of detected people`;
    $("#example-helmet-count").textContent = state.helmet_count || 0;
    $("#example-no-helmet-count").textContent = state.no_helmet_count || 0;
    $("#example-helmet-percent").textContent = `${Number(state.helmet_percent || 0).toFixed(1)}% of detected people`;
    $("#example-no-helmet-percent").textContent = `${Number(state.no_helmet_percent || 0).toFixed(1)}% of detected people`;
  } catch (error) {
    $("#error-banner").textContent = error.message;
    $("#error-banner").classList.remove("hidden");
  }
}

loadHistory();
refreshStatus();
window.setInterval(refreshStatus, 1200);
window.setInterval(() => {
  if (["dashboard", "history", "videos", "reports"].some((view) => $(`#view-${view}`).classList.contains("active"))) loadHistory();
}, 5000);

async function restoreViewFromHash() {
  const route = window.location.hash.slice(1);
  if (route.startsWith("detail/")) {
    try {
      await openDetectionDetail(decodeURIComponent(route.slice("detail/".length)), false);
    } catch {
      $("#error-banner").textContent = "Invalid detection details link.";
      $("#error-banner").classList.remove("hidden");
    }
    return;
  }
  if (titles[route] && route !== "detail") showView(route, false);
}

window.addEventListener("hashchange", restoreViewFromHash);
restoreViewFromHash();
