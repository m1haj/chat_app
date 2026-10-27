"use strict";

const form = document.querySelector("#chat-form");
const cameraInput = document.querySelector("#camera-input");
const galleryInput = document.querySelector("#gallery-input");
const legacyInput = document.querySelector("#image-input");
const promptInput = document.querySelector("#prompt-input");
const preview = document.querySelector("#image-preview");
const previewImage = document.querySelector("#preview-image");
const previewName = document.querySelector("#preview-name");
const previewStatus = document.querySelector("#preview-status");
const removeImageButton = document.querySelector("#remove-image");
const sendButton = document.querySelector("#send-button");
const conversation = document.querySelector("#conversation");
const welcome = document.querySelector("#welcome");
const formError = document.querySelector("#form-error");

let currentFile = null;
let previewUrl = null;
let isSubmitting = false;

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getSafeAsciiFilename(originalName) {
  if (!originalName || typeof originalName !== "string") {
    return "photo.jpg";
  }
  let safe = originalName
    .normalize("NFKD")
    .replace(/[^\x00-\x7F]/g, "")
    .replace(/[^a-zA-Z0-9._-]/g, "_")
    .replace(/_{2,}/g, "_")
    .trim();

  if (!safe || safe === ".jpg" || safe === ".jpeg" || safe === ".png" || safe === ".webp") {
    safe = "photo.jpg";
  }
  if (!/\.(jpe?g|png|webp)$/i.test(safe)) {
    safe = `${safe.replace(/\.[^.]+$/, "")}.jpg`;
  }
  return safe.toLowerCase();
}

/**
 * Resizes large phone photos in the browser and converts browser-decodable
 * image formats (including iPhone HEIC) to standard JPEG before upload.
 * Returns a Blob or original File, avoiding buggy `new File()` constructor on iOS.
 */
async function processAndResizeImage(file, maxDimension = 1400, quality = 0.85) {
  if (!file || (!file.type.startsWith("image/") && !/\.(jpe?g|png|webp|heic|heif)$/i.test(file.name || ""))) {
    return file;
  }

  return new Promise((resolve) => {
    let url = "";
    try {
      url = URL.createObjectURL(file);
    } catch (_) {
      return resolve(file);
    }

    const img = new Image();

    img.onload = () => {
      try {
        URL.revokeObjectURL(url);
      } catch (_) {}

      try {
        let width = img.naturalWidth || img.width;
        let height = img.naturalHeight || img.height;

        if (!width || !height) {
          return resolve(file);
        }

        const isHeic = /heic|heif/i.test(file.type || "") || /\.(heic|heif)$/i.test(file.name || "");
        const needsResize = width > maxDimension || height > maxDimension;

        // If already small and not HEIC, keep original
        if (!needsResize && !isHeic && file.size < 2 * 1024 * 1024) {
          return resolve(file);
        }

        if (needsResize) {
          if (width > height) {
            height = Math.round((height * maxDimension) / width);
            width = maxDimension;
          } else {
            width = Math.round((width * maxDimension) / height);
            height = maxDimension;
          }
        }

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          return resolve(file);
        }

        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(0, 0, width, height);
        try {
          ctx.imageSmoothingEnabled = true;
          ctx.imageSmoothingQuality = "high";
        } catch (_) {}
        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob(
          (blob) => {
            if (!blob) {
              return resolve(file);
            }
            resolve(blob);
          },
          "image/jpeg",
          quality
        );
      } catch (err) {
        console.warn("Canvas resize failed, falling back to original file:", err);
        resolve(file);
      }
    };

    img.onerror = () => {
      try {
        URL.revokeObjectURL(url);
      } catch (_) {}
      // Fallback: If canvas decode fails, pass original file for server validation
      resolve(file);
    };

    img.src = url;
  });
}

function clearPreview() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  currentFile = null;
  if (cameraInput) cameraInput.value = "";
  if (galleryInput) galleryInput.value = "";
  if (legacyInput) legacyInput.value = "";
  preview.hidden = true;
  previewImage.removeAttribute("src");
  previewName.textContent = "";
  if (previewStatus) previewStatus.textContent = "";
}

function showError(message) {
  formError.textContent = message;
  formError.hidden = false;
}

function setFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/") && !/\.(jpe?g|png|webp|heic|heif)$/i.test(file.name)) {
    clearPreview();
    showError("Please choose a photo (JPEG, PNG, WEBP, or HEIC).");
    return;
  }
  formError.hidden = true;
  currentFile = file;

  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  previewImage.src = previewUrl;
  previewName.textContent = file.name;
  if (previewStatus) {
    previewStatus.textContent = `${formatFileSize(file.size)} · Ready to attach`;
  }
  preview.hidden = false;
}

function addUserMessage(text, imageFile) {
  const message = document.createElement("div");
  message.className = "message user";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text || "Please take a look at this image.";
  message.append(body);
  if (imageFile) {
    const image = document.createElement("img");
    image.className = "message-image";
    image.alt = "Image attached with this question";
    image.src = URL.createObjectURL(imageFile);
    message.append(image);
  }
  conversation.append(message);
}

function formatMarkdown(text) {
  if (!text) return "";
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Bold **text**
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Italic *text*
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  // Headings
  html = html.replace(/^### (.*$)/gim, '<h4 class="md-heading">$1</h4>');
  html = html.replace(/^## (.*$)/gim, '<h3 class="md-heading">$1</h3>');
  html = html.replace(/^# (.*$)/gim, '<h2 class="md-heading">$1</h2>');

  const lines = html.split("\n");
  let inList = false;
  const processed = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (/^[*-]\s+(.*)$/.test(trimmed)) {
      if (!inList) {
        processed.push('<ul class="md-list">');
        inList = true;
      }
      processed.push(`<li>${trimmed.replace(/^[*-]\s+/, "")}</li>`);
    } else {
      if (inList) {
        processed.push("</ul>");
        inList = false;
      }
      if (trimmed.length > 0) {
        if (!trimmed.startsWith("<h")) {
          processed.push(`<p class="md-para">${trimmed}</p>`);
        } else {
          processed.push(trimmed);
        }
      }
    }
  }
  if (inList) processed.push("</ul>");
  return processed.join("");
}

function showToast(text) {
  const existing = document.querySelector(".copy-toast");
  if (existing) existing.remove();
  const toast = document.createElement("div");
  toast.className = "copy-toast";
  toast.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> ${text}`;
  document.body.append(toast);
  setTimeout(() => toast.remove(), 2600);
}

function addAssistantMessage(result) {
  const message = document.createElement("div");
  message.className = "message assistant";

  const card = document.createElement("div");
  card.className = "assistant-card";

  // 1. Triage Banner
  const triage = (result.triage || "uncertain").toLowerCase();
  const isUrgent = result.urgent || triage === "urgent";
  const banner = document.createElement("div");
  banner.className = `triage-banner ${isUrgent ? "urgent" : triage}`;

  let iconText = "✓";
  let title = "Routine Guidance";
  let desc = "No acute red flags observed in this photo. General supportive skin care advice below.";

  if (isUrgent) {
    iconText = "!";
    title = "Urgent Attention Recommended";
    desc = "Potential red-flag symptoms detected. Please consult an emergency provider or doctor promptly.";
  } else if (triage === "uncertain") {
    iconText = "?";
    title = "In-Person Clinical Evaluation Recommended";
    desc = "Image clarity or symptoms are inconclusive. Have a licensed clinician inspect the area in person.";
  }

  banner.innerHTML = `
    <div class="triage-banner-icon">${iconText}</div>
    <div class="triage-banner-content">
      <div class="triage-banner-title">${title}</div>
      <div class="triage-banner-desc">${desc}</div>
    </div>
  `;
  card.append(banner);

  // 2. Synthesized Body with Markdown Formatting
  const body = document.createElement("div");
  body.className = "message-body";
  body.innerHTML = formatMarkdown(result.answer);
  card.append(body);

  // 3. Clinical Sources
  if (Array.isArray(result.sources) && result.sources.length) {
    const sourcesWrapper = document.createElement("div");
    sourcesWrapper.className = "sources-section";
    const sourcesTitle = document.createElement("div");
    sourcesTitle.className = "sources-title";
    sourcesTitle.textContent = "Verified Clinical References";
    sourcesWrapper.append(sourcesTitle);

    const pills = document.createElement("div");
    pills.className = "sources-pills";

    for (const source of result.sources) {
      let domain = "";
      try {
        domain = new URL(source.url).hostname.replace(/^www\./, "");
      } catch (_) {}

      const link = document.createElement("a");
      link.className = "source-pill";
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.innerHTML = `
        <span>${source.title || domain || "Clinical Link"}</span>
        ${domain ? `<span class="source-domain">${domain}</span>` : ""}
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      `;
      pills.append(link);
    }
    sourcesWrapper.append(pills);
    card.append(sourcesWrapper);
  }

  // 4. Action Toolbar: Copy Doctor Summary & Red Flag Checklist
  const toolbar = document.createElement("div");
  toolbar.className = "action-toolbar";

  // Button: Copy Doctor Summary
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "action-btn";
  copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy Doctor Summary`;

  copyBtn.addEventListener("click", () => {
    const dateStr = new Date().toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    const summaryText = [
      `[Skin Bot Consultation Summary - ${dateStr}]`,
      `Triage Level: ${triage.toUpperCase()}`,
      `Urgent Flag: ${isUrgent ? "YES (Evaluation Advised)" : "No immediate red flags"}`,
      "",
      `Assessment Guidance:`,
      result.answer.replace(/[*#]/g, ""),
      "",
      `References:`,
      ...(result.sources || []).map((s) => `- ${s.title}: ${s.url}`),
      "",
      `*Disclaimer: Educational AI assistance. Consult a licensed doctor for personal diagnosis.*`
    ].join("\n");

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(summaryText).then(() => {
        showToast("Summary copied to clipboard for your doctor!");
      }).catch(() => {
        showToast("Unable to copy to clipboard.");
      });
    } else {
      showToast("Clipboard unavailable in browser.");
    }
  });
  toolbar.append(copyBtn);

  // Button: Interactive Red Flag Self-Check
  const redFlagBtn = document.createElement("button");
  redFlagBtn.type = "button";
  redFlagBtn.className = "action-btn";
  redFlagBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> Red Flag Checklist`;

  const redFlagBox = document.createElement("div");
  redFlagBox.className = "redflags-box";
  redFlagBox.hidden = true;
  redFlagBox.innerHTML = `
    <div class="redflags-header">
      <span>Emergency Signs Self-Check</span>
      <span style="font-size: 11px; font-weight: normal; color: #9a3412;">Select any that apply</span>
    </div>
    <div class="redflags-list">
      <label class="redflag-item"><input type="checkbox" class="rf-chk" value="fever"> Fever higher than 100.4°F (38°C)</label>
      <label class="redflag-item"><input type="checkbox" class="rf-chk" value="spread"> Redness spreading rapidly within hours</label>
      <label class="redflag-item"><input type="checkbox" class="rf-chk" value="breath"> Shortness of breath, dizziness, or facial swelling</label>
      <label class="redflag-item"><input type="checkbox" class="rf-chk" value="pain"> Severe or disproportionate skin pain or tenderness</label>
      <label class="redflag-item"><input type="checkbox" class="rf-chk" value="blister"> Extensive skin peeling or blistering</label>
    </div>
    <div class="redflag-alert">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>One or more red flags selected. Please seek urgent care or emergency medical evaluation immediately.</span>
    </div>
  `;

  redFlagBtn.addEventListener("click", () => {
    redFlagBox.hidden = !redFlagBox.hidden;
    redFlagBtn.classList.toggle("active", !redFlagBox.hidden);
  });

  const checkboxes = redFlagBox.querySelectorAll(".rf-chk");
  const alertBox = redFlagBox.querySelector(".redflag-alert");
  checkboxes.forEach((chk) => {
    chk.addEventListener("change", () => {
      const anyChecked = Array.from(checkboxes).some((c) => c.checked);
      alertBox.classList.toggle("visible", anyChecked);
    });
  });

  toolbar.append(redFlagBtn);
  card.append(toolbar);
  card.append(redFlagBox);

  message.append(card);
  conversation.append(message);
}

function addLoadingMessage() {
  const message = document.createElement("div");
  message.className = "message assistant";
  message.id = "loading-message";
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = "Analyzing… this can take up to a minute";
  const sub = document.createElement("div");
  sub.className = "loading-subtext";
  sub.textContent = "Reviewing image safety, urgent signs, and clinical guidance…";
  const dots = document.createElement("div");
  dots.className = "loading-dots";
  dots.setAttribute("aria-label", "Loading response");
  for (let index = 0; index < 3; index += 1) dots.append(document.createElement("span"));
  message.append(label, sub, dots);
  try {
    message.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (_) {
    try {
      message.scrollIntoView();
    } catch (_) {}
  }
  return message;
}

if (cameraInput) {
  cameraInput.addEventListener("change", () => {
    const file = cameraInput.files?.[0];
    if (file) setFile(file);
  });
}

if (galleryInput) {
  galleryInput.addEventListener("change", () => {
    const file = galleryInput.files?.[0];
    if (file) setFile(file);
  });
}

if (legacyInput) {
  legacyInput.addEventListener("change", () => {
    const file = legacyInput.files?.[0];
    if (file) setFile(file);
  });
}

removeImageButton.addEventListener("click", clearPreview);

promptInput.addEventListener("input", () => {
  promptInput.style.height = "auto";
  promptInput.style.height = `${Math.min(promptInput.scrollHeight, 130)}px`;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isSubmitting) return; // Prevent double tap / duplicate submit

  formError.hidden = true;
  if (!currentFile) {
    showError("Add a photo using the Camera or Gallery button before sending.");
    return;
  }

  isSubmitting = true;
  sendButton.disabled = true;
  if (cameraInput) cameraInput.disabled = true;
  if (galleryInput) galleryInput.disabled = true;
  if (legacyInput) legacyInput.disabled = true;
  promptInput.disabled = true;
  removeImageButton.disabled = true;

  const prompt = promptInput.value.trim();
  const fileToUpload = currentFile;

  if (welcome) welcome.remove();
  addUserMessage(prompt, fileToUpload);
  const loading = addLoadingMessage();
  clearPreview();

  try {
    // Shrink photo in the browser and convert HEIC to JPEG
    const processedImage = await processAndResizeImage(fileToUpload);

    if (processedImage.size > 8 * 1024 * 1024) {
      throw new Error("The photo exceeds the 8 MB upload limit even after resizing. Please choose a smaller photo.");
    }

    const safeFilename = getSafeAsciiFilename(fileToUpload.name);
    const payload = new FormData();
    payload.append("image", processedImage, safeFilename);
    payload.append("prompt", prompt);

    const response = await fetch("/api/chat", { method: "POST", body: payload });
    const responseText = await response.text();
    let result = null;
    try {
      result = JSON.parse(responseText);
    } catch (_) {
      // not JSON
    }

    if (!response.ok) {
      const detail =
        result && result.detail
          ? result.detail
          : `Server error (${response.status}): ${responseText.slice(0, 150) || "Unable to complete request"}`;
      throw new Error(detail);
    }

    if (!result || typeof result !== "object") {
      throw new Error("Invalid response format received from server.");
    }

    addAssistantMessage(result);
  } catch (error) {
    const message = document.createElement("div");
    message.className = "message assistant";
    message.setAttribute("role", "alert");
    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = "Unable to respond";
    const body = document.createElement("div");
    body.className = "message-body";
    body.textContent = error instanceof Error ? error.message : "Please try again later.";
    message.append(label, body);
    conversation.append(message);
  } finally {
    loading.remove();
    isSubmitting = false;
    sendButton.disabled = false;
    if (cameraInput) cameraInput.disabled = false;
    if (galleryInput) galleryInput.disabled = false;
    if (legacyInput) legacyInput.disabled = false;
    promptInput.disabled = false;
    removeImageButton.disabled = false;
    promptInput.value = "";
    promptInput.style.height = "auto";
    promptInput.focus();
  }
});