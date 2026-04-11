const form = document.getElementById("download-form");
const urlInput = document.getElementById("url");
const loadFormatsBtn = document.getElementById("load-formats");
const qualitySelect = document.getElementById("quality");
const formatsStatusEl = document.getElementById("formats-status");
const downloadBtn = document.getElementById("download-btn");
const statusCardEl = document.getElementById("status-card");
const statusPhaseEl = document.getElementById("status-phase");
const statusSpinnerEl = document.getElementById("status-spinner");
const statusMessageEl = document.getElementById("status-message");
const statusMetaEl = document.getElementById("status-meta");
const statusRawEl = document.getElementById("status-raw");
const filesEl = document.getElementById("files");
const refreshBtn = document.getElementById("refresh-files");

let pollTimer = null;
let loadedFormatsUrl = "";

function formatTime(isoTime) {
    if (!isoTime) {
        return "";
    }

    const parsed = new Date(isoTime);
    if (Number.isNaN(parsed.getTime())) {
        return "";
    }

    return parsed.toLocaleTimeString();
}

function mapStatus(payload) {
    const status = String(payload?.status || "").toLowerCase();
    const hasError = Boolean(payload?.error);
    const explicitMessage = String(payload?.message || "").trim();

    if (status === "queued") {
        return {
            state: "queued",
            phase: "Queued",
            message: explicitMessage || "Request accepted. Preparing download...",
            loading: true,
        };
    }

    if (status === "downloading") {
        return {
            state: "downloading",
            phase: "Downloading",
            message: explicitMessage || "Downloading video...",
            loading: true,
        };
    }

    if (status === "completed") {
        const fileName = payload?.result?.file_name;
        const premiereSafe = Boolean(payload?.result?.premiere_safe_audio);
        const codec = String(payload?.result?.audio_codec || "").toUpperCase();
        const sampleRate = payload?.result?.audio_sample_rate;
        const channels = payload?.result?.audio_channels;

        const compatNote = premiereSafe
            ? ` Premiere-safe audio: ${codec || "AAC"}${sampleRate ? ` ${sampleRate}Hz` : ""}${channels ? ` ${channels}ch` : ""}.`
            : "";

        return {
            state: "completed",
            phase: "Completed",
            message: fileName
                ? `Saved: ${fileName}.${compatNote}`
                : `Download completed successfully.${compatNote}`,
            loading: false,
        };
    }

    if (status === "failed" || hasError) {
        return {
            state: "failed",
            phase: "Failed",
            message: payload?.error || explicitMessage || "Download failed.",
            loading: false,
        };
    }

    return {
        state: "idle",
        phase: "Idle",
        message: explicitMessage || "Waiting for start...",
        loading: false,
    };
}

function setStatus(data) {
    const payload = data && typeof data === "object" ? data : { message: String(data) };
    const mapped = mapStatus(payload);

    statusCardEl.dataset.state = mapped.state;
    statusPhaseEl.textContent = mapped.phase;
    statusMessageEl.textContent = mapped.message;
    statusSpinnerEl.hidden = !mapped.loading;

    const meta = [];
    if (payload.task_id) {
        meta.push(`Task: ${payload.task_id}`);
    }
    const updated = formatTime(payload.updated_at || payload.created_at);
    if (updated) {
        meta.push(`Updated: ${updated}`);
    }
    statusMetaEl.textContent = meta.join(" • ");

    statusRawEl.textContent = JSON.stringify(payload, null, 2);
}

function setFormatsStatus(message, isError = false) {
    formatsStatusEl.textContent = message;
    formatsStatusEl.classList.toggle("error", isError);
}

function formatBytes(bytes) {
    if (!bytes || bytes <= 0) {
        return "~ size unknown";
    }
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatLabel(format) {
    const parts = [];
    if (format.quality) {
        parts.push(format.quality);
    } else if (format.resolution) {
        parts.push(format.resolution);
    }
    if (format.ext) {
        parts.push(String(format.ext).toUpperCase());
    }
    if (format.fps) {
        parts.push(`${format.fps} fps`);
    }
    if (format.filesize) {
        parts.push(formatBytes(format.filesize));
    }
    if (format.note) {
        parts.push(`(${format.note})`);
    }
    return parts.join(" • ");
}

function resetFormats() {
    qualitySelect.innerHTML = "<option value=\"\">Load qualities first</option>";
    qualitySelect.disabled = true;
    downloadBtn.disabled = true;
    loadedFormatsUrl = "";
}

async function loadFormats() {
    const url = urlInput.value.trim();
    if (!url) {
        setFormatsStatus("Enter URL first", true);
        resetFormats();
        return;
    }

    setFormatsStatus("Loading available qualities...");
    loadFormatsBtn.disabled = true;
    qualitySelect.disabled = true;
    downloadBtn.disabled = true;

    try {
        const response = await fetch(`/api/formats?url=${encodeURIComponent(url)}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Failed to load qualities");
        }

        const formats = Array.isArray(data.formats) ? data.formats : [];
        if (formats.length === 0) {
            throw new Error("No quality options found for this URL");
        }

        qualitySelect.innerHTML = "";

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Select quality";
        qualitySelect.appendChild(placeholder);

        formats.forEach((format) => {
            const option = document.createElement("option");
            option.value = format.format_id;
            option.textContent = formatLabel(format);
            qualitySelect.appendChild(option);
        });

        qualitySelect.disabled = false;
        qualitySelect.selectedIndex = 1;
        downloadBtn.disabled = false;
        loadedFormatsUrl = url;
        setFormatsStatus(`Loaded ${formats.length} quality options`);
    } catch (error) {
        resetFormats();
        setFormatsStatus(String(error), true);
        setStatus({ error: String(error) });
    } finally {
        loadFormatsBtn.disabled = false;
    }
}

async function loadFiles() {
    const response = await fetch("/api/files");
    const data = await response.json();
    filesEl.innerHTML = "";

    if (!data.files || data.files.length === 0) {
        const li = document.createElement("li");
        li.textContent = "No files yet";
        filesEl.appendChild(li);
        return;
    }

    data.files.forEach((file) => {
        const li = document.createElement("li");
        const mb = (file.size_bytes / (1024 * 1024)).toFixed(2);
        li.textContent = `${file.name} (${mb} MB)`;
        filesEl.appendChild(li);
    });
}

async function pollStatus(taskId) {
    if (pollTimer) {
        clearInterval(pollTimer);
    }

    pollTimer = setInterval(async () => {
        try {
            const response = await fetch(`/api/status/${taskId}`);
            const data = await response.json();
            setStatus(data);

            if (data.status === "completed" || data.status === "failed") {
                clearInterval(pollTimer);
                pollTimer = null;
                await loadFiles();
                downloadBtn.disabled = !qualitySelect.value;
            }
        } catch (error) {
            setStatus({
                status: "downloading",
                task_id: taskId,
                message: "Download is still running. Waiting for next status update...",
                warning: String(error),
            });
        }
    }, 1500);
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const url = urlInput.value.trim();
    if (!url) {
        setStatus({ status: "failed", error: "Enter a URL" });
        return;
    }

    const formatId = qualitySelect.value;
    if (!formatId || loadedFormatsUrl !== url) {
        setStatus({ status: "failed", error: "Load qualities and choose one option before downloading" });
        return;
    }

    setStatus({ status: "queued", message: "Sending download request..." });
    downloadBtn.disabled = true;

    try {
        const response = await fetch("/api/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, format_id: formatId }),
        });

        const data = await response.json();
        setStatus(data);

        if (response.ok && data.task_id) {
            await pollStatus(data.task_id);
        } else {
            downloadBtn.disabled = false;
        }
    } catch (error) {
        setStatus({ status: "failed", error: String(error), message: "Failed to start download" });
        downloadBtn.disabled = false;
    }
});

loadFormatsBtn.addEventListener("click", () => {
    loadFormats().catch((error) => {
        setFormatsStatus(String(error), true);
        setStatus({ error: String(error) });
    });
});

urlInput.addEventListener("input", () => {
    if (urlInput.value.trim() !== loadedFormatsUrl) {
        resetFormats();
        setFormatsStatus("URL changed. Load qualities again.");
    }
});

qualitySelect.addEventListener("change", () => {
    downloadBtn.disabled = !qualitySelect.value;
});

refreshBtn.addEventListener("click", () => {
    loadFiles().catch((error) => setStatus({ status: "failed", error: String(error) }));
});

setStatus({ status: "idle", message: "Waiting for start..." });
loadFiles().catch((error) => setStatus({ status: "failed", error: String(error) }));
